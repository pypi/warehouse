# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import hashlib
import tempfile

import pretend
import pytest

from pydantic import TypeAdapter
from pypi_attestations import (
    Attestation,
    AttestationBundle,
    AttestationType,
    Envelope,
    GitHubPublisher,
    GitLabPublisher,
    Provenance,
    VerificationError,
    VerificationMaterial,
)
from sigstore.verify import Verifier
from zope.interface.verify import verifyClass

from tests.common.db.oidc import GitHubPublisherFactory, GitLabPublisherFactory
from tests.common.db.packaging import FileEventFactory, FileFactory
from warehouse.attestations import (
    Attestation as DatabaseAttestation,
    AttestationUploadError,
    IIntegrityService,
    IntegrityService,
    UnsupportedPublisherError,
    services,
)
from warehouse.events.tags import EventTag
from warehouse.metrics import IMetricsService
from warehouse.packaging import File, IFileStorage

VALID_ATTESTATION = Attestation(
    version=1,
    verification_material=VerificationMaterial(
        certificate="somebase64string", transparency_entries=[dict()]
    ),
    envelope=Envelope(
        statement="somebase64string",
        signature="somebase64string",
    ),
)


class TestAttestationsService:
    def test_interface_matches(self):
        assert verifyClass(IIntegrityService, IntegrityService)

    def test_create_service(self):
        request = pretend.stub(
            find_service=pretend.call_recorder(
                lambda svc, context=None, name=None: None
            ),
        )

        assert IntegrityService.create_service(None, request) is not None
        assert not set(request.find_service.calls) ^ {
            pretend.call(IFileStorage),
            pretend.call(IMetricsService),
        }

    def test_persist_attestations(self, db_request, monkeypatch):
        @pretend.call_recorder
        def storage_service_store(path: str, file_path, *_args, **_kwargs):
            expected = VALID_ATTESTATION.model_dump_json().encode("utf-8")
            with open(file_path, "rb") as fp:
                assert fp.read() == expected

            assert path.endswith(".attestation")

        integrity_service = IntegrityService(
            storage=pretend.stub(
                store=storage_service_store,
            ),
            metrics=pretend.stub(),
        )

        file = FileFactory.create(attestations=[])

        integrity_service.persist_attestations([VALID_ATTESTATION], file)

        attestations_db = (
            db_request.db.query(DatabaseAttestation)
            .join(DatabaseAttestation.file)
            .filter(File.filename == file.filename)
            .all()
        )
        assert len(attestations_db) == 1
        assert len(file.attestations) == 1

    def test_parse_no_publisher(self, db_request):
        integrity_service = IntegrityService(
            storage=pretend.stub(),
            metrics=pretend.stub(),
        )

        db_request.oidc_publisher = None
        with pytest.raises(
            AttestationUploadError,
            match="Attestations are only supported when using Trusted",
        ):
            integrity_service.parse_attestations(db_request, pretend.stub())

    def test_parse_unsupported_publisher(self, db_request):
        integrity_service = IntegrityService(
            storage=pretend.stub(),
            metrics=pretend.stub(),
        )
        db_request.oidc_publisher = pretend.stub(publisher_name="not-existing")
        with pytest.raises(
            AttestationUploadError,
            match="Attestations are only supported when using Trusted",
        ):
            integrity_service.parse_attestations(db_request, pretend.stub())

    def test_parse_malformed_attestation(self, metrics, db_request):
        integrity_service = IntegrityService(
            storage=pretend.stub(),
            metrics=metrics,
        )

        db_request.oidc_publisher = pretend.stub(publisher_name="GitHub")
        db_request.POST["attestations"] = "{'malformed-attestation'}"
        with pytest.raises(
            AttestationUploadError,
            match="Error while decoding the included attestation",
        ):
            integrity_service.parse_attestations(db_request, pretend.stub())

        assert (
            pretend.call("warehouse.upload.attestations.malformed")
            in metrics.increment.calls
        )

    def test_parse_multiple_attestations(self, metrics, db_request):
        integrity_service = IntegrityService(
            storage=pretend.stub(),
            metrics=metrics,
        )

        db_request.oidc_publisher = pretend.stub(publisher_name="GitHub")
        db_request.POST["attestations"] = TypeAdapter(list[Attestation]).dump_json(
            [VALID_ATTESTATION, VALID_ATTESTATION]
        )
        with pytest.raises(
            AttestationUploadError, match="Only a single attestation per file"
        ):
            integrity_service.parse_attestations(
                db_request,
                pretend.stub(),
            )

        assert (
            pretend.call("warehouse.upload.attestations.failed_multiple_attestations")
            in metrics.increment.calls
        )

    @pytest.mark.parametrize(
        ("verify_exception", "expected_message"),
        [
            (
                VerificationError,
                "Could not verify the uploaded",
            ),
            (
                ValueError,
                "Unknown error while",
            ),
        ],
    )
    def test_parse_failed_verification(
        self, metrics, monkeypatch, db_request, verify_exception, expected_message
    ):
        integrity_service = IntegrityService(
            storage=pretend.stub(),
            metrics=metrics,
        )

        db_request.oidc_publisher = pretend.stub(
            publisher_name="GitHub",
            publisher_verification_policy=pretend.call_recorder(lambda c: None),
        )
        db_request.oidc_claims = {"sha": "somesha"}
        db_request.POST["attestations"] = TypeAdapter(list[Attestation]).dump_json(
            [VALID_ATTESTATION]
        )

        def failing_verify(_self, _verifier, _policy, _dist):
            raise verify_exception("error")

        monkeypatch.setattr(Verifier, "production", lambda: pretend.stub())
        monkeypatch.setattr(Attestation, "verify", failing_verify)

        with pytest.raises(AttestationUploadError, match=expected_message):
            integrity_service.parse_attestations(
                db_request,
                pretend.stub(),
            )

    def test_parse_wrong_predicate(self, metrics, monkeypatch, db_request):
        integrity_service = IntegrityService(
            storage=pretend.stub(),
            metrics=metrics,
        )
        db_request.oidc_publisher = pretend.stub(
            publisher_name="GitHub",
            publisher_verification_policy=pretend.call_recorder(lambda c: None),
        )
        db_request.oidc_claims = {"sha": "somesha"}
        db_request.POST["attestations"] = TypeAdapter(list[Attestation]).dump_json(
            [VALID_ATTESTATION]
        )

        monkeypatch.setattr(Verifier, "production", lambda: pretend.stub())
        monkeypatch.setattr(
            Attestation, "verify", lambda *args: ("wrong-predicate", {})
        )

        with pytest.raises(
            AttestationUploadError, match="Attestation with unsupported predicate"
        ):
            integrity_service.parse_attestations(
                db_request,
                pretend.stub(),
            )

        assert (
            pretend.call(
                "warehouse.upload.attestations.failed_unsupported_predicate_type"
            )
            in metrics.increment.calls
        )

    def test_parse_succeed(self, metrics, monkeypatch, db_request):
        integrity_service = IntegrityService(
            storage=pretend.stub(),
            metrics=metrics,
        )
        db_request.oidc_publisher = pretend.stub(
            publisher_name="GitHub",
            publisher_verification_policy=pretend.call_recorder(lambda c: None),
        )
        db_request.oidc_claims = {"sha": "somesha"}
        db_request.POST["attestations"] = TypeAdapter(list[Attestation]).dump_json(
            [VALID_ATTESTATION]
        )

        monkeypatch.setattr(Verifier, "production", lambda: pretend.stub())
        monkeypatch.setattr(
            Attestation, "verify", lambda *args: (AttestationType.PYPI_PUBLISH_V1, {})
        )

        attestations = integrity_service.parse_attestations(
            db_request,
            pretend.stub(),
        )
        assert attestations == [VALID_ATTESTATION]

    def test_generate_provenance_unsupported_publisher(self):
        integrity_service = IntegrityService(
            storage=pretend.stub(),
            metrics=pretend.stub(),
        )

        oidc_publisher = pretend.stub(publisher_name="not-existing")

        assert (
            integrity_service.generate_provenance(oidc_publisher, pretend.stub())
            is None
        )

    @pytest.mark.parametrize(
        "publisher_name",
        [
            "github",
            "gitlab",
        ],
    )
    def test_generate_provenance_succeeds(self, publisher_name: str, monkeypatch):
        integrity_service = IntegrityService(
            storage=pretend.stub(),
            metrics=pretend.stub(),
        )

        if publisher_name == "github":
            publisher = GitHubPublisher(
                repository="fake-repository",
                workflow="fake-workflow",
            )
        else:
            publisher = GitLabPublisher(
                repository="fake-repository",
                environment="fake-env",
            )

        monkeypatch.setattr(
            services,
            "_publisher_from_oidc_publisher",
            lambda s: publisher,
        )

        provenance = integrity_service.generate_provenance(
            pretend.stub(),
            [VALID_ATTESTATION],
        )

        assert provenance == Provenance(
            attestation_bundles=[
                AttestationBundle(
                    publisher=publisher,
                    attestations=[VALID_ATTESTATION],
                )
            ]
        )

    def test_persist_provenance_succeeds(self, db_request):
        provenance = Provenance(
            attestation_bundles=[
                AttestationBundle(
                    publisher=GitHubPublisher(
                        repository="fake-repository",
                        workflow="fake-workflow",
                    ),
                    attestations=[VALID_ATTESTATION],
                )
            ]
        )

        @pretend.call_recorder
        def storage_service_store(path, file_path, *_args, **_kwargs):
            expected = provenance.model_dump_json().encode("utf-8")
            with open(file_path, "rb") as fp:
                assert fp.read() == expected

            assert path.suffix == ".provenance"

        integrity_service = IntegrityService(
            storage=pretend.stub(store=storage_service_store),
            metrics=pretend.stub(),
        )
        assert (
            integrity_service.persist_provenance(provenance, FileFactory.create())
            is None
        )

    def test_get_provenance_digest(self, db_request):
        file = FileFactory.create()
        FileEventFactory.create(
            source=file,
            tag=EventTag.File.FileAdd,
            additional={"publisher_url": "fake-publisher-url"},
        )

        with tempfile.NamedTemporaryFile() as f:
            integrity_service = IntegrityService(
                storage=pretend.stub(get=pretend.call_recorder(lambda p: f)),
                metrics=pretend.stub(),
            )

            assert (
                integrity_service.get_provenance_digest(file)
                == hashlib.file_digest(f, "sha256").hexdigest()
            )

    def test_get_provenance_digest_fails_no_attestations(self, db_request):
        # If the attestations are missing, there is no provenance file
        file = FileFactory.create()
        file.attestations = []
        FileEventFactory.create(
            source=file,
            tag=EventTag.File.FileAdd,
            additional={"publisher_url": "fake-publisher-url"},
        )
        integrity_service = IntegrityService(
            storage=pretend.stub(),
            metrics=pretend.stub(),
        )

        assert integrity_service.get_provenance_digest(file) is None


def test_publisher_from_oidc_publisher_github(db_request):
    publisher = GitHubPublisherFactory.create()

    attestation_publisher = services._publisher_from_oidc_publisher(publisher)
    assert isinstance(attestation_publisher, GitHubPublisher)
    assert attestation_publisher.repository == publisher.repository
    assert attestation_publisher.workflow == publisher.workflow_filename
    assert attestation_publisher.environment == publisher.environment


def test_publisher_from_oidc_publisher_gitlab(db_request):
    publisher = GitLabPublisherFactory.create()

    attestation_publisher = services._publisher_from_oidc_publisher(publisher)
    assert isinstance(attestation_publisher, GitLabPublisher)
    assert attestation_publisher.repository == publisher.project_path
    assert attestation_publisher.environment == publisher.environment


def test_publisher_from_oidc_publisher_fails():
    publisher = pretend.stub(publisher_name="not-existing")

    with pytest.raises(UnsupportedPublisherError):
        services._publisher_from_oidc_publisher(publisher)
