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
from tests.common.db.packaging import FileFactory
from warehouse.attestations import (
    Attestation as DatabaseAttestation,
    AttestationUploadError,
    IIntegrityService,
    IntegrityService,
    UnsupportedPublisherError,
    services,
)
from warehouse.packaging import File

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


class TestNullIntegrityService:
    def test_interface_matches(self):
        assert verifyClass(IIntegrityService, services.NullIntegrityService)

    def test_get_provenance_digest(self, db_request):
        db_request.oidc_publisher = pretend.stub(
            publisher_name="GitHub",
            repository="fake/fake",
            workflow_filename="fake.yml",
            environment="fake",
        )

        file = FileFactory.create()
        service = services.NullIntegrityService()

        provenance = service.generate_provenance(db_request, file, [VALID_ATTESTATION])
        assert isinstance(provenance, Provenance)

        provenance_digest = service.get_provenance_digest(file)
        assert isinstance(provenance_digest, str)


class TestIntegrityService:
    def test_interface_matches(self):
        assert verifyClass(IIntegrityService, IntegrityService)

    def test_create_service(self, db_request):
        service = IntegrityService.create_service(None, db_request)
        assert service is not None
        assert service.storage.base.exists()

    def test_persist_attestations_succeeds(self, db_request, storage_service):
        integrity_service = IntegrityService(
            storage=storage_service,
            metrics=pretend.stub(),
        )

        file = FileFactory.create()
        integrity_service._persist_attestations([VALID_ATTESTATION], file)

        attestations_db = (
            db_request.db.query(DatabaseAttestation)
            .join(DatabaseAttestation.file)
            .filter(File.filename == file.filename)
            .all()
        )
        assert len(attestations_db) == 1
        assert len(file.attestations) == 1

        attestation_path = attestations_db[0].attestation_path

        assert attestation_path.endswith(".attestation")
        assert (
            storage_service.get(attestation_path).read()
            == VALID_ATTESTATION.model_dump_json().encode()
        )

    def test_parse_attestations_fails_no_publisher(self, db_request):
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

    def test_parse_attestations_fails_unsupported_publisher(self, db_request):
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

    def test_parse_attestations_fails_malformed_attestation(self, metrics, db_request):
        integrity_service = IntegrityService(
            storage=pretend.stub(),
            metrics=metrics,
        )

        db_request.oidc_publisher = pretend.stub(publisher_name="GitHub")
        db_request.POST["attestations"] = "{'malformed-attestation'}"
        with pytest.raises(
            AttestationUploadError,
            match="Malformed attestations",
        ):
            integrity_service.parse_attestations(db_request, pretend.stub())

        assert (
            pretend.call("warehouse.upload.attestations.malformed")
            in metrics.increment.calls
        )

    def test_parse_attestations_fails_multiple_attestations(self, metrics, db_request):
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
    def test_parse_attestations_fails_verification(
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

    def test_parse_attestations_fails_wrong_predicate(
        self, metrics, monkeypatch, db_request
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

    def test_parse_attestations_succeeds(self, metrics, monkeypatch, db_request):
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

    def test_generate_provenance_fails_unsupported_publisher(self, db_request, metrics):
        integrity_service = IntegrityService(
            storage=pretend.stub(),
            metrics=pretend.stub(),
        )

        db_request.oidc_publisher = pretend.stub(publisher_name="not-existing")

        file = FileFactory.create()
        assert (
            integrity_service.generate_provenance(db_request, file, [VALID_ATTESTATION])
            is None
        )

        # If the generate provenance fails, verify that no attestations are stored
        assert not file.attestations

    @pytest.mark.parametrize(
        "publisher_factory",
        [
            GitHubPublisherFactory,
            GitLabPublisherFactory,
        ],
    )
    def test_generate_provenance_succeeds(
        self, db_request, metrics, storage_service, publisher_factory
    ):
        integrity_service = IntegrityService(
            storage=storage_service,
            metrics=metrics,
        )

        file = FileFactory.create()

        db_request.oidc_publisher = publisher_factory.create()
        provenance = integrity_service.generate_provenance(
            db_request,
            file,
            [VALID_ATTESTATION],
        )

        expected_provenance = Provenance(
            attestation_bundles=[
                AttestationBundle(
                    publisher=services._publisher_from_oidc_publisher(
                        db_request.oidc_publisher
                    ),
                    attestations=[VALID_ATTESTATION],
                )
            ]
        )

        assert provenance == expected_provenance

        # We can round-trip the provenance object out of storage.
        provenance_from_store = Provenance.model_validate_json(
            storage_service.get(f"{file.path}.provenance").read()
        )
        assert provenance_from_store == expected_provenance == provenance

        # Generate provenance also persist attestations
        assert (
            storage_service.get(file.attestations[0].attestation_path).read()
            == VALID_ATTESTATION.model_dump_json().encode()
        )

    def test_persist_provenance_succeeds(self, db_request, storage_service, metrics):
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

        integrity_service = IntegrityService(
            storage=storage_service,
            metrics=metrics,
        )
        file = FileFactory.create()
        assert integrity_service._persist_provenance(provenance, file) is None

        assert (
            storage_service.get(f"{file.path}.provenance").read()
            == provenance.model_dump_json().encode()
        )

    def test_get_provenance_digest_succeeds(self, db_request, metrics, storage_service):
        file = FileFactory.create()

        integrity_service = IntegrityService(
            storage=storage_service,
            metrics=metrics,
        )

        db_request.oidc_publisher = GitHubPublisherFactory.create()

        integrity_service.generate_provenance(db_request, file, [VALID_ATTESTATION])
        provenance_file = f"{file.path}.provenance"

        assert (
            integrity_service.get_provenance_digest(file)
            == hashlib.file_digest(
                storage_service.get(provenance_file), "sha256"
            ).hexdigest()
        )

    def test_get_provenance_digest_fails_no_attestations(self, db_request):
        # If the attestations are missing, there is no provenance file
        file = FileFactory.create()
        integrity_service = IntegrityService(
            storage=pretend.stub(),
            metrics=pretend.stub(),
        )

        assert integrity_service.get_provenance_digest(file) is None


def test_publisher_from_oidc_publisher_succeeds_github(db_request):
    publisher = GitHubPublisherFactory.create()

    attestation_publisher = services._publisher_from_oidc_publisher(publisher)
    assert isinstance(attestation_publisher, GitHubPublisher)
    assert attestation_publisher.repository == publisher.repository
    assert attestation_publisher.workflow == publisher.workflow_filename
    assert attestation_publisher.environment == publisher.environment


def test_publisher_from_oidc_publisher_succeeds_gitlab(db_request):
    publisher = GitLabPublisherFactory.create()

    attestation_publisher = services._publisher_from_oidc_publisher(publisher)
    assert isinstance(attestation_publisher, GitLabPublisher)
    assert attestation_publisher.repository == publisher.project_path
    assert attestation_publisher.environment == publisher.environment


def test_publisher_from_oidc_publisher_fails_unsupported():
    publisher = pretend.stub(publisher_name="not-existing")

    with pytest.raises(UnsupportedPublisherError):
        services._publisher_from_oidc_publisher(publisher)
