# SPDX-License-Identifier: Apache-2.0

import json
import re

import pretend
import pytest

from pydantic import TypeAdapter
from pypi_attestations import (
    Attestation,
    AttestationType,
    Provenance,
    VerificationError,
)
from sigstore.verify import Verifier
from zope.interface.verify import verifyClass

from tests.common.db.oidc import (
    ActiveStatePublisherFactory,
    GitHubPublisherFactory,
    GitLabPublisherFactory,
    GooglePublisherFactory,
)
from tests.common.db.packaging import FileFactory
from warehouse.attestations import IIntegrityService, services
from warehouse.attestations.errors import AttestationUploadError
from warehouse.attestations.models import Provenance as DatabaseProvenance


class TestNullIntegrityService:
    def test_interface_matches(self):
        assert verifyClass(IIntegrityService, services.NullIntegrityService)

    @pytest.mark.parametrize(
        "publisher_factory",
        [GitHubPublisherFactory, GitLabPublisherFactory, GooglePublisherFactory],
    )
    def test_build_provenance(self, db_request, dummy_attestation, publisher_factory):
        db_request.oidc_publisher = publisher_factory.create()

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

    @pytest.mark.parametrize(
        "publisher_factory",
        [
            ActiveStatePublisherFactory,
        ],
    )
    def test_parse_attestations_fails_unsupported_publisher(
        self, db_request, publisher_factory
    ):
        integrity_service = services.IntegrityService(
            metrics=pretend.stub(), session=db_request.db
        )
        db_request.oidc_publisher = publisher_factory.create()
        with pytest.raises(
            AttestationUploadError,
            match=(
                "Attestations are not currently supported with "
                f"{db_request.oidc_publisher.publisher_name} publishers"
            ),
        ):
            integrity_service.parse_attestations(db_request, pretend.stub())

    def test_parse_attestations_fails_malformed_attestation(self, metrics, db_request):
        integrity_service = services.IntegrityService(
            metrics=metrics,
            session=db_request.db,
        )

        db_request.oidc_publisher = pretend.stub(attestation_identity=pretend.stub())
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

    def test_parse_attestations_fails_multiple_attestations_exceeds_limit(
        self, metrics, db_request, dummy_attestation
    ):
        integrity_service = services.IntegrityService(
            metrics=metrics,
            session=db_request.db,
        )

        max_attestations = len(services.SUPPORTED_ATTESTATION_TYPES)

        db_request.oidc_publisher = pretend.stub(attestation_identity=pretend.stub())
        db_request.POST["attestations"] = TypeAdapter(list[Attestation]).dump_json(
            [dummy_attestation] * (max_attestations + 1)
        )
        with pytest.raises(
            AttestationUploadError,
            match=f"A maximum of {max_attestations} attestations per file are "
            f"supported",
        ):
            integrity_service.parse_attestations(
                db_request,
                pretend.stub(),
            )

        assert (
            pretend.call(
                "warehouse.upload.attestations.failed_limit_multiple_attestations"
            )
            in metrics.increment.calls
        )

    def test_parse_attestations_fails_multiple_attestations_same_predicate(
        self, metrics, monkeypatch, db_request, dummy_attestation
    ):
        integrity_service = services.IntegrityService(
            metrics=metrics,
            session=db_request.db,
        )
        max_attestations = len(services.SUPPORTED_ATTESTATION_TYPES)
        db_request.oidc_publisher = pretend.stub(
            attestation_identity=pretend.stub(),
        )
        db_request.oidc_claims = {"sha": "somesha"}
        db_request.POST["attestations"] = TypeAdapter(list[Attestation]).dump_json(
            [dummy_attestation] * max_attestations
        )

        monkeypatch.setattr(Verifier, "production", lambda: pretend.stub())
        monkeypatch.setattr(
            Attestation, "verify", lambda *args: (AttestationType.PYPI_PUBLISH_V1, {})
        )

        with pytest.raises(
            AttestationUploadError,
            match=re.escape(
                "Multiple attestations for the same file with the same predicate "
                "type (https://docs.pypi.org/attestations/publish/v1) are not supported"
            ),
        ):
            integrity_service.parse_attestations(
                db_request,
                pretend.stub(),
            )

        assert (
            pretend.call(
                "warehouse.upload.attestations.failed_duplicate_predicate_type"
            )
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
            attestation_identity=pretend.stub(),
        )
        db_request.oidc_claims = {"sha": "somesha"}
        db_request.POST["attestations"] = TypeAdapter(list[Attestation]).dump_json(
            [dummy_attestation]
        )

        def failing_verify(_self, _policy, _dist):
            raise verify_exception("error")

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
            attestation_identity=pretend.stub(),
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
            attestation_identity=pretend.stub(),
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

    @pytest.mark.parametrize(
        "publisher_factory",
        [GitHubPublisherFactory, GitLabPublisherFactory, GooglePublisherFactory],
    )
    def test_build_provenance_succeeds(
        self, metrics, db_request, publisher_factory, dummy_attestation
    ):
        db_request.oidc_publisher = publisher_factory.create()

        integrity_service = services.IntegrityService(
            metrics=metrics,
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

        assert metrics.increment.calls == [
            pretend.call("warehouse.attestations.build_provenance.ok")
        ]


@pytest.mark.parametrize(
    "publisher_factory",
    [GitHubPublisherFactory, GitLabPublisherFactory, GooglePublisherFactory],
)
def test_extract_attestations_from_request_empty_list(db_request, publisher_factory):
    db_request.oidc_publisher = publisher_factory.create()
    db_request.POST = {"attestations": json.dumps([])}

    with pytest.raises(
        AttestationUploadError, match="an empty attestation set is not permitted"
    ):
        services._extract_attestations_from_request(db_request)
