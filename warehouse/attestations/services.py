# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import typing
import warnings

import sentry_sdk

from pydantic import TypeAdapter, ValidationError
from pypi_attestations import (
    Attestation,
    AttestationBundle,
    AttestationType,
    Distribution,
    Provenance,
    VerificationError,
)
from pyramid.request import Request
from zope.interface import implementer

from warehouse.attestations.errors import AttestationUploadError
from warehouse.attestations.interfaces import IIntegrityService
from warehouse.attestations.models import Provenance as DatabaseProvenance
from warehouse.metrics.interfaces import IMetricsService
from warehouse.utils.exceptions import InsecureIntegrityServiceWarning

if typing.TYPE_CHECKING:
    from warehouse.packaging.models import File


SUPPORTED_ATTESTATION_TYPES = {
    AttestationType.PYPI_PUBLISH_V1,
    AttestationType.SLSA_PROVENANCE_V1,
}


def _extract_attestations_from_request(request: Request) -> list[Attestation]:
    """
    Extract well-formed attestation objects from the given request's payload.
    """

    if not request.oidc_publisher:
        raise AttestationUploadError(
            "Attestations are only supported when using Trusted Publishing"
        )

    if not request.oidc_publisher.attestation_identity:
        raise AttestationUploadError(
            "Attestations are not currently supported with "
            f"{request.oidc_publisher.publisher_name} publishers"
        )

    metrics = request.find_service(IMetricsService, context=None)

    try:
        attestations = TypeAdapter(list[Attestation]).validate_json(
            request.POST["attestations"]
        )
    except ValidationError as e:
        # Log invalid (malformed) attestation upload
        metrics.increment("warehouse.upload.attestations.malformed")
        raise AttestationUploadError(
            f"Malformed attestations: {e}",
        )

    # Empty attestation sets are not permitted; users should omit `attestations`
    # entirely to upload without attestations.
    if not attestations:
        raise AttestationUploadError(
            "Malformed attestations: an empty attestation set is not permitted"
        )

    # We currently allow at most one attestation per predicate type
    max_attestations = len(SUPPORTED_ATTESTATION_TYPES)
    if len(attestations) > max_attestations:
        metrics.increment(
            "warehouse.upload.attestations.failed_limit_multiple_attestations"
        )
        raise AttestationUploadError(
            f"A maximum of {max_attestations} attestations per file are supported",
        )

    return attestations


@implementer(IIntegrityService)
class NullIntegrityService:
    def __init__(self, session):
        warnings.warn(
            "NullIntegrityService is intended only for use in development, "
            "you should not use it in production due to the lack of actual "
            "attestation verification.",
            InsecureIntegrityServiceWarning,
        )
        self.db = session

    @classmethod
    def create_service(cls, _context, request):
        return cls(session=request.db)

    def parse_attestations(
        self, request: Request, _distribution: Distribution
    ) -> list[Attestation]:
        return _extract_attestations_from_request(request)

    def build_provenance(
        self, request: Request, file: File, attestations: list[Attestation]
    ) -> DatabaseProvenance:
        attestation_bundle = AttestationBundle(
            publisher=request.oidc_publisher.attestation_identity,
            attestations=attestations,
        )

        provenance = Provenance(attestation_bundles=[attestation_bundle]).model_dump(
            mode="json"
        )

        return DatabaseProvenance(file=file, provenance=provenance)


@implementer(IIntegrityService)
class IntegrityService:
    def __init__(self, metrics: IMetricsService, session):
        self.metrics: IMetricsService = metrics
        self.db = session

    @classmethod
    def create_service(cls, _context, request):
        return cls(
            metrics=request.find_service(IMetricsService),
            session=request.db,
        )

    def parse_attestations(
        self, request: Request, distribution: Distribution
    ) -> list[Attestation]:
        """
        Process any attestations included in a file upload request

        Attestations, if present, will be parsed and verified against the uploaded
        artifact. Attestations are only allowed when uploading via a Trusted
        Publisher, because a Trusted Publisher provides the identity that will be
        used to verify the attestations.
        """

        attestations = _extract_attestations_from_request(request)

        # Sanity-checked above.
        expected_identity = request.oidc_publisher.attestation_identity

        seen_predicate_types: set[AttestationType] = set()

        for attestation_model in attestations:
            try:
                predicate_type_str, _ = attestation_model.verify(
                    expected_identity,
                    distribution,
                )
            except VerificationError as e:
                # Log invalid (failed verification) attestation upload
                self.metrics.increment("warehouse.upload.attestations.failed_verify")
                raise AttestationUploadError(
                    f"Could not verify the uploaded artifact using the included "
                    f"attestation: {e}",
                )
            except Exception as e:
                with sentry_sdk.new_scope() as scope:
                    scope.fingerprint = [e]
                    sentry_sdk.capture_message(
                        f"Unexpected error while verifying attestation: {e}"
                    )

                raise AttestationUploadError(
                    f"Unknown error while trying to verify included attestations: {e}",
                )

            if predicate_type_str not in SUPPORTED_ATTESTATION_TYPES:
                self.metrics.increment(
                    "warehouse.upload.attestations.failed_unsupported_predicate_type"
                )
                raise AttestationUploadError(
                    f"Attestation with unsupported predicate type: "
                    f"{predicate_type_str}",
                )
            predicate_type = AttestationType(predicate_type_str)

            if predicate_type in seen_predicate_types:
                self.metrics.increment(
                    "warehouse.upload.attestations.failed_duplicate_predicate_type"
                )
                raise AttestationUploadError(
                    f"Multiple attestations for the same file with the same "
                    f"predicate type ({predicate_type.value}) are not supported",
                )

            seen_predicate_types.add(predicate_type)

        return attestations

    def build_provenance(
        self, request: Request, file: File, attestations: list[Attestation]
    ) -> DatabaseProvenance:
        attestation_bundle = AttestationBundle(
            publisher=request.oidc_publisher.attestation_identity,
            attestations=attestations,
        )

        provenance = Provenance(attestation_bundles=[attestation_bundle]).model_dump(
            mode="json"
        )
        db_provenance = DatabaseProvenance(file=file, provenance=provenance)

        self.metrics.increment("warehouse.attestations.build_provenance.ok")
        return db_provenance
