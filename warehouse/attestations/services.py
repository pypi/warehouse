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

from __future__ import annotations

import hashlib
import typing
import warnings

import rfc8785
import sentry_sdk

from pydantic import TypeAdapter, ValidationError
from pypi_attestations import (
    Attestation,
    AttestationBundle,
    AttestationType,
    Distribution,
    GitHubPublisher,
    GitLabPublisher,
    Provenance,
    Publisher,
    VerificationError,
)
from pyramid.request import Request
from sigstore.verify import Verifier
from zope.interface import implementer

from warehouse.attestations.errors import AttestationUploadError
from warehouse.attestations.interfaces import IIntegrityService
from warehouse.attestations.models import Provenance as DatabaseProvenance
from warehouse.metrics.interfaces import IMetricsService
from warehouse.oidc.models import (
    GitHubPublisher as GitHubOIDCPublisher,
    GitLabPublisher as GitLabOIDCPublisher,
    OIDCPublisher,
)
from warehouse.utils.exceptions import InsecureIntegrityServiceWarning

if typing.TYPE_CHECKING:
    from warehouse.packaging.models import File


def _publisher_from_oidc_publisher(publisher: OIDCPublisher) -> Publisher:
    """
    Convert an OIDCPublisher object in a pypi-attestations Publisher.
    """
    match publisher.publisher_name:
        case "GitLab":
            publisher = typing.cast(GitLabOIDCPublisher, publisher)
            return GitLabPublisher(
                repository=publisher.project_path, environment=publisher.environment
            )
        case "GitHub":
            publisher = typing.cast(GitHubOIDCPublisher, publisher)
            return GitHubPublisher(
                repository=publisher.repository,
                workflow=publisher.workflow_filename,
                environment=publisher.environment,
            )
        case _:
            raise AttestationUploadError(
                f"Unsupported publisher: {publisher.publisher_name}"
            )


def _build_provenance(
    request: Request, file: File, attestations: list[Attestation]
) -> DatabaseProvenance:
    try:
        publisher: Publisher = _publisher_from_oidc_publisher(request.oidc_publisher)
    except AttestationUploadError as exc:
        sentry_sdk.capture_message(
            f"Unsupported OIDCPublisher found {request.oidc_publisher.publisher_name}"
        )
        raise exc

    attestation_bundle = AttestationBundle(
        publisher=publisher,
        attestations=attestations,
    )

    provenance = Provenance(attestation_bundles=[attestation_bundle]).model_dump(
        mode="json"
    )

    db_provenance = DatabaseProvenance(
        file=file,
        provenance=provenance,
        provenance_digest=hashlib.sha256(rfc8785.dumps(provenance)).hexdigest(),
    )

    return db_provenance


def _extract_attestations_from_request(request: Request) -> list[Attestation]:
    """
    Extract well-formed attestation objects from the given request's payload.
    """

    publisher: OIDCPublisher | None = request.oidc_publisher
    if not publisher:
        raise AttestationUploadError(
            "Attestations are only supported when using Trusted Publishing"
        )
    if not publisher.supports_attestations:
        raise AttestationUploadError(
            "Attestations are not currently supported with "
            f"{publisher.publisher_name} publishers"
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

    # This is a temporary constraint; multiple attestations per file will
    # be supported in the future.
    if len(attestations) > 1:
        metrics.increment("warehouse.upload.attestations.failed_multiple_attestations")

        raise AttestationUploadError(
            "Only a single attestation per file is supported",
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
        return _build_provenance(request, file, attestations)


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
        Only GitHub Actions Trusted Publishers are supported.
        """

        attestations = _extract_attestations_from_request(request)

        # The above attestation extraction guarantees that we have a publisher.
        publisher: OIDCPublisher = request.oidc_publisher

        verification_policy = publisher.publisher_verification_policy(
            request.oidc_claims
        )
        for attestation_model in attestations:
            try:
                predicate_type, _ = attestation_model.verify(
                    Verifier.production(),
                    verification_policy,
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
                with sentry_sdk.push_scope() as scope:
                    scope.fingerprint = [e]
                    sentry_sdk.capture_message(
                        f"Unexpected error while verifying attestation: {e}"
                    )

                raise AttestationUploadError(
                    f"Unknown error while trying to verify included attestations: {e}",
                )

            if predicate_type != AttestationType.PYPI_PUBLISH_V1:
                self.metrics.increment(
                    "warehouse.upload.attestations.failed_unsupported_predicate_type"
                )
                raise AttestationUploadError(
                    f"Attestation with unsupported predicate type: {predicate_type}",
                )

        return attestations

    def build_provenance(
        self, request: Request, file: File, attestations: list[Attestation]
    ) -> DatabaseProvenance:
        return _build_provenance(request, file, attestations)
