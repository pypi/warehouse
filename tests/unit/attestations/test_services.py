# SPDX-License-Identifier: Apache-2.0

import json
import re

import pytest

from pydantic import TypeAdapter
from pypi_attestations import (
    Attestation,
    AttestationType,
    Provenance,
    VerificationError,
)
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


def attestations_json(attestations):
    """Serialize ``attestations`` as the upload form's ``attestations`` value."""
    return TypeAdapter(list[Attestation]).dump_json(attestations).decode()


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

    def test_parse_attestations(self, db_request, mocker):
        service = services.NullIntegrityService.create_service(None, db_request)

        extract_attestations_from_request = mocker.patch.object(
            services, "_extract_attestations_from_request", autospec=True
        )

        attestations = service.parse_attestations(
            db_request, mocker.sentinel.distribution
        )

        assert attestations is extract_attestations_from_request.return_value
        extract_attestations_from_request.assert_called_once_with(db_request)


class TestIntegrityService:
    @pytest.fixture
    def github_request(self, db_request):
        """A request authenticated by a GitHub Trusted Publisher."""
        db_request.oidc_publisher = GitHubPublisherFactory.build()
        return db_request

    def test_interface_matches(self):
        assert verifyClass(IIntegrityService, services.IntegrityService)

    def test_create_service(self, db_request):
        service = services.IntegrityService.create_service(None, db_request)
        assert isinstance(service, services.IntegrityService)

    def test_parse_attestations_fails_no_publisher(self, metrics, db_request, mocker):
        integrity_service = services.IntegrityService(
            metrics=metrics,
            session=db_request.db,
        )

        db_request.oidc_publisher = None
        with pytest.raises(
            AttestationUploadError,
            match="Attestations are only supported when using Trusted Publishing",
        ):
            integrity_service.parse_attestations(
                db_request, mocker.sentinel.distribution
            )

        metrics.increment.assert_not_called()

    @pytest.mark.parametrize(
        "publisher_factory",
        [
            ActiveStatePublisherFactory,
        ],
    )
    def test_parse_attestations_fails_unsupported_publisher(
        self, metrics, db_request, publisher_factory, mocker
    ):
        integrity_service = services.IntegrityService(
            metrics=metrics, session=db_request.db
        )
        db_request.oidc_publisher = publisher_factory.create()
        with pytest.raises(
            AttestationUploadError,
            match=(
                "Attestations are not currently supported with "
                f"{db_request.oidc_publisher.publisher_name} publishers"
            ),
        ):
            integrity_service.parse_attestations(
                db_request, mocker.sentinel.distribution
            )

        metrics.increment.assert_not_called()

    def test_parse_attestations_fails_malformed_attestation(
        self, metrics, github_request, mocker
    ):
        integrity_service = services.IntegrityService(
            metrics=metrics,
            session=github_request.db,
        )

        github_request.POST["attestations"] = "{'malformed-attestation'}"
        with pytest.raises(
            AttestationUploadError,
            match="Malformed attestations",
        ):
            integrity_service.parse_attestations(
                github_request, mocker.sentinel.distribution
            )

        assert metrics.increment.call_args_list == [
            mocker.call("warehouse.upload.attestations.malformed")
        ]

    def test_parse_attestations_fails_multiple_attestations_exceeds_limit(
        self, metrics, github_request, dummy_attestation, mocker
    ):
        integrity_service = services.IntegrityService(
            metrics=metrics,
            session=github_request.db,
        )

        max_attestations = len(services.SUPPORTED_ATTESTATION_TYPES)

        github_request.POST["attestations"] = attestations_json(
            [dummy_attestation] * (max_attestations + 1)
        )
        with pytest.raises(
            AttestationUploadError,
            match=f"A maximum of {max_attestations} attestations per file are "
            f"supported",
        ):
            integrity_service.parse_attestations(
                github_request, mocker.sentinel.distribution
            )

        assert metrics.increment.call_args_list == [
            mocker.call(
                "warehouse.upload.attestations.failed_limit_multiple_attestations"
            )
        ]

    def test_parse_attestations_fails_multiple_attestations_same_predicate(
        self, metrics, github_request, dummy_attestation, mocker
    ):
        integrity_service = services.IntegrityService(
            metrics=metrics,
            session=github_request.db,
        )
        max_attestations = len(services.SUPPORTED_ATTESTATION_TYPES)
        github_request.POST["attestations"] = attestations_json(
            [dummy_attestation] * max_attestations
        )

        verify = mocker.patch.object(
            Attestation,
            "verify",
            autospec=True,
            return_value=(AttestationType.PYPI_PUBLISH_V1, {}),
        )

        with pytest.raises(
            AttestationUploadError,
            match=re.escape(
                "Multiple attestations for the same file with the same predicate "
                "type (https://docs.pypi.org/attestations/publish/v1) are not supported"
            ),
        ):
            integrity_service.parse_attestations(
                github_request, mocker.sentinel.distribution
            )

        assert (
            verify.call_args_list
            == [
                mocker.call(
                    dummy_attestation,
                    github_request.oidc_publisher.attestation_identity,
                    mocker.sentinel.distribution,
                )
            ]
            * 2
        )
        assert metrics.increment.call_args_list == [
            mocker.call("warehouse.upload.attestations.failed_duplicate_predicate_type")
        ]

    @pytest.mark.parametrize(
        ("verify_exception", "expected_message", "expected_metrics", "sentry_messages"),
        [
            (
                VerificationError,
                "Could not verify the uploaded",
                ["warehouse.upload.attestations.failed_verify"],
                [],
            ),
            (
                ValueError,
                "Unknown error while",
                [],
                ["Unexpected error while verifying attestation: error"],
            ),
        ],
    )
    def test_parse_attestations_fails_verification(
        self,
        metrics,
        github_request,
        dummy_attestation,
        verify_exception,
        expected_message,
        expected_metrics,
        sentry_messages,
        mocker,
    ):
        sentry_sdk = mocker.patch.object(services, "sentry_sdk", autospec=True)
        integrity_service = services.IntegrityService(
            metrics=metrics,
            session=github_request.db,
        )

        github_request.POST["attestations"] = attestations_json([dummy_attestation])

        verify = mocker.patch.object(
            Attestation,
            "verify",
            autospec=True,
            side_effect=verify_exception("error"),
        )

        with pytest.raises(AttestationUploadError, match=expected_message):
            integrity_service.parse_attestations(
                github_request, mocker.sentinel.distribution
            )

        verify.assert_called_once_with(
            dummy_attestation,
            github_request.oidc_publisher.attestation_identity,
            mocker.sentinel.distribution,
        )
        assert metrics.increment.call_args_list == [
            mocker.call(name) for name in expected_metrics
        ]
        assert sentry_sdk.capture_message.call_args_list == [
            mocker.call(message) for message in sentry_messages
        ]

    def test_parse_attestations_fails_wrong_predicate(
        self,
        metrics,
        github_request,
        dummy_attestation,
        mocker,
    ):
        integrity_service = services.IntegrityService(
            metrics=metrics,
            session=github_request.db,
        )
        github_request.POST["attestations"] = attestations_json([dummy_attestation])

        verify = mocker.patch.object(
            Attestation, "verify", autospec=True, return_value=("wrong-predicate", {})
        )

        with pytest.raises(
            AttestationUploadError, match="Attestation with unsupported predicate"
        ):
            integrity_service.parse_attestations(
                github_request, mocker.sentinel.distribution
            )

        verify.assert_called_once_with(
            dummy_attestation,
            github_request.oidc_publisher.attestation_identity,
            mocker.sentinel.distribution,
        )
        assert metrics.increment.call_args_list == [
            mocker.call(
                "warehouse.upload.attestations.failed_unsupported_predicate_type"
            )
        ]

    def test_parse_attestations_succeeds(
        self, metrics, github_request, dummy_attestation, mocker
    ):
        integrity_service = services.IntegrityService(
            metrics=metrics,
            session=github_request.db,
        )
        github_request.POST["attestations"] = attestations_json([dummy_attestation])

        verify = mocker.patch.object(
            Attestation,
            "verify",
            autospec=True,
            return_value=(AttestationType.PYPI_PUBLISH_V1, {}),
        )

        attestations = integrity_service.parse_attestations(
            github_request, mocker.sentinel.distribution
        )
        assert attestations == [dummy_attestation]
        verify.assert_called_once_with(
            dummy_attestation,
            github_request.oidc_publisher.attestation_identity,
            mocker.sentinel.distribution,
        )
        metrics.increment.assert_not_called()

    @pytest.mark.parametrize(
        "publisher_factory",
        [GitHubPublisherFactory, GitLabPublisherFactory, GooglePublisherFactory],
    )
    def test_build_provenance_succeeds(
        self, metrics, db_request, publisher_factory, dummy_attestation, mocker
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

        assert metrics.increment.call_args_list == [
            mocker.call("warehouse.attestations.build_provenance.ok")
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
