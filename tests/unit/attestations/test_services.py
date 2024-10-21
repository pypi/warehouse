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
import json

import pretend
import pytest

from pydantic import TypeAdapter
from pypi_attestations import (
    Attestation,
    AttestationType,
    GitHubPublisher,
    GitLabPublisher,
    Provenance,
    VerificationError,
)
from sigstore.verify import Verifier
from zope.interface.verify import verifyClass

from tests.common.db.oidc import GitHubPublisherFactory, GitLabPublisherFactory
from tests.common.db.packaging import FileFactory
from warehouse.attestations import IIntegrityService, services
from warehouse.attestations.errors import AttestationUploadError
from warehouse.attestations.models import Provenance as DatabaseProvenance


class TestNullIntegrityService:
    def test_interface_matches(self):
        assert verifyClass(IIntegrityService, services.NullIntegrityService)

    def test_build_provenance(self, db_request, dummy_attestation):
        db_request.oidc_publisher = pretend.stub(
            publisher_name="GitHub",
            repository="fake/fake",
            workflow_filename="fake.yml",
            environment="fake",
        )

        file = FileFactory.create()
        service = services.NullIntegrityService.create_service(None, db_request)

        provenance = service.build_provenance(db_request, file, [dummy_attestation])
        assert isinstance(provenance, DatabaseProvenance)
        assert provenance.file == file
        assert file.provenance == provenance

    def test_parse_attestations(self, db_request, monkeypatch):
        service = services.NullIntegrityService.create_service(None, db_request)

        extract_attestations_from_request = pretend.call_recorder(lambda r: None)
        monkeypatch.setattr(
            services,
            "_extract_attestations_from_request",
            extract_attestations_from_request,
        )

        service.parse_attestations(db_request, pretend.stub())
        assert extract_attestations_from_request.calls == [pretend.call(db_request)]


class TestIntegrityService:
    def test_interface_matches(self):
        assert verifyClass(IIntegrityService, services.IntegrityService)

    def test_create_service(self, db_request):
        service = services.IntegrityService.create_service(None, db_request)
        assert isinstance(service, services.IntegrityService)

    def test_parse_attestations_fails_no_publisher(self, db_request):
        integrity_service = services.IntegrityService(
            metrics=pretend.stub(),
            session=db_request.db,
        )

        db_request.oidc_publisher = None
        with pytest.raises(
            AttestationUploadError,
            match="Attestations are only supported when using Trusted Publishing",
        ):
            integrity_service.parse_attestations(db_request, pretend.stub())

    def test_parse_attestations_fails_unsupported_publisher(self, db_request):
        integrity_service = services.IntegrityService(
            metrics=pretend.stub(), session=db_request.db
        )
        db_request.oidc_publisher = pretend.stub(
            supports_attestations=False, publisher_name="fake"
        )
        with pytest.raises(
            AttestationUploadError,
            match="Attestations are not currently supported with fake publishers",
        ):
            integrity_service.parse_attestations(db_request, pretend.stub())

    def test_parse_attestations_fails_malformed_attestation(self, metrics, db_request):
        integrity_service = services.IntegrityService(
            metrics=metrics,
            session=db_request.db,
        )

        db_request.oidc_publisher = pretend.stub(supports_attestations=True)
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

    def test_parse_attestations_fails_multiple_attestations(
        self, metrics, db_request, dummy_attestation
    ):
        integrity_service = services.IntegrityService(
            metrics=metrics,
            session=db_request.db,
        )

        db_request.oidc_publisher = pretend.stub(supports_attestations=True)
        db_request.POST["attestations"] = TypeAdapter(list[Attestation]).dump_json(
            [dummy_attestation, dummy_attestation]
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
        self,
        metrics,
        monkeypatch,
        db_request,
        dummy_attestation,
        verify_exception,
        expected_message,
    ):
        integrity_service = services.IntegrityService(
            metrics=metrics,
            session=db_request.db,
        )

        db_request.oidc_publisher = pretend.stub(
            supports_attestations=True,
            publisher_verification_policy=pretend.call_recorder(lambda c: None),
        )
        db_request.oidc_claims = {"sha": "somesha"}
        db_request.POST["attestations"] = TypeAdapter(list[Attestation]).dump_json(
            [dummy_attestation]
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
        self,
        metrics,
        monkeypatch,
        db_request,
        dummy_attestation,
    ):
        integrity_service = services.IntegrityService(
            metrics=metrics,
            session=db_request.db,
        )
        db_request.oidc_publisher = pretend.stub(
            supports_attestations=True,
            publisher_verification_policy=pretend.call_recorder(lambda c: None),
        )
        db_request.oidc_claims = {"sha": "somesha"}
        db_request.POST["attestations"] = TypeAdapter(list[Attestation]).dump_json(
            [dummy_attestation]
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

    def test_parse_attestations_succeeds(
        self, metrics, monkeypatch, db_request, dummy_attestation
    ):
        integrity_service = services.IntegrityService(
            metrics=metrics,
            session=db_request.db,
        )
        db_request.oidc_publisher = pretend.stub(
            supports_attestations=True,
            publisher_verification_policy=pretend.call_recorder(lambda c: None),
        )
        db_request.oidc_claims = {"sha": "somesha"}
        db_request.POST["attestations"] = TypeAdapter(list[Attestation]).dump_json(
            [dummy_attestation]
        )

        monkeypatch.setattr(Verifier, "production", lambda: pretend.stub())
        monkeypatch.setattr(
            Attestation, "verify", lambda *args: (AttestationType.PYPI_PUBLISH_V1, {})
        )

        attestations = integrity_service.parse_attestations(
            db_request,
            pretend.stub(),
        )
        assert attestations == [dummy_attestation]

    def test_build_provenance_fails_unsupported_publisher(
        self, db_request, dummy_attestation
    ):
        integrity_service = services.IntegrityService(
            metrics=pretend.stub(),
            session=db_request.db,
        )

        db_request.oidc_publisher = pretend.stub(publisher_name="not-existing")

        file = FileFactory.create()
        with pytest.raises(AttestationUploadError, match="Unsupported publisher"):
            integrity_service.build_provenance(db_request, file, [dummy_attestation])

        # If building provenance fails, nothing is stored or associated with the file
        assert not file.provenance

    @pytest.mark.parametrize(
        "publisher_factory",
        [
            GitHubPublisherFactory,
            GitLabPublisherFactory,
        ],
    )
    def test_build_provenance_succeeds(
        self, db_request, publisher_factory, dummy_attestation
    ):
        db_request.oidc_publisher = publisher_factory.create()

        integrity_service = services.IntegrityService(
            metrics=pretend.stub(),
            session=db_request.db,
        )

        file = FileFactory.create()
        assert file.provenance is None

        provenance = integrity_service.build_provenance(
            db_request, file, [dummy_attestation]
        )
        assert file.provenance == provenance

        model = Provenance.model_validate(provenance.provenance)
        assert model.attestation_bundles[0].attestations == [dummy_attestation]


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

    with pytest.raises(AttestationUploadError):
        services._publisher_from_oidc_publisher(publisher)


def test_extract_attestations_from_request_empty_list(db_request):
    db_request.oidc_publisher = GitHubPublisherFactory.create()
    db_request.POST = {"attestations": json.dumps([])}

    with pytest.raises(
        AttestationUploadError, match="an empty attestation set is not permitted"
    ):
        services._extract_attestations_from_request(db_request)
