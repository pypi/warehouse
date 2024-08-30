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
import typing
import warnings

from pathlib import Path

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

from warehouse.attestations.errors import (
    AttestationUploadError,
    UnsupportedPublisherError,
)
from warehouse.attestations.interfaces import IIntegrityService
from warehouse.attestations.models import Attestation as DatabaseAttestation
from warehouse.metrics.interfaces import IMetricsService
from warehouse.oidc.models import (
    GitHubPublisher as GitHubOIDCPublisher,
    GitLabPublisher as GitLabOIDCPublisher,
    OIDCPublisher,
)
from warehouse.packaging.interfaces import IFileStorage
from warehouse.packaging.models import File
from warehouse.utils.exceptions import InsecureIntegrityServiceWarning


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
            raise UnsupportedPublisherError


def _extract_attestations_from_request(request: Request) -> list[Attestation]:
    """
    Extract well-formed attestation objects from the given request's payload.
    """

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

    def generate_provenance(
        self, request: Request, file: File, attestations: list[Attestation]
    ) -> Provenance | None:
        publisher = _publisher_from_oidc_publisher(request.oidc_publisher)
        attestation_bundle = AttestationBundle(
            publisher=publisher,
            attestations=attestations,
        )
        provenance = Provenance(attestation_bundles=[attestation_bundle])

        for attestation in attestations:
            self.db.add(
                DatabaseAttestation(
                    file=file,
                    attestation_file_blake2_digest=hashlib.blake2b(
                        attestation.model_dump_json().encode("utf-8")
                    ).hexdigest(),
                )
            )

        return provenance

    def get_provenance_digest(self, file: File) -> str | None:
        if not file.attestations:
            return None

        # For the null service, our "provenance digest" is just the digest
        # of the release file's name merged with the number of attestations.
        # We do this because there's no verification involved; we just need
        # a unique value to preserve invariants.
        return hashlib.sha256(
            f"{file.filename}:{len(file.attestations)}".encode()
        ).hexdigest()


@implementer(IIntegrityService)
class IntegrityService:
    def __init__(self, storage: IFileStorage, metrics: IMetricsService, session):
        self.storage: IFileStorage = storage
        self.metrics: IMetricsService = metrics
        self.db = session

    @classmethod
    def create_service(cls, _context, request):
        return cls(
            storage=request.find_service(IFileStorage, name="archive"),
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
        publisher: OIDCPublisher | None = request.oidc_publisher
        if not publisher or not publisher.publisher_name == "GitHub":
            raise AttestationUploadError(
                "Attestations are only supported when using Trusted "
                "Publishing with GitHub Actions.",
            )

        attestations = _extract_attestations_from_request(request)

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

    def generate_provenance(
        self, request: Request, file: File, attestations: list[Attestation]
    ) -> Provenance | None:

        # Generate the provenance object.
        provenance = self._build_provenance_object(request.oidc_publisher, attestations)

        if not provenance:
            return None

        # Persist the attestations and provenance objects. We only do this
        # after generating the provenance above, to prevent orphaned artifacts
        # on any generation failures.
        self._persist_attestations(attestations, file)
        self._persist_provenance(provenance, file)

        return provenance

    def get_provenance_digest(self, file: File) -> str | None:
        """Returns the sha256 digest of the provenance file for the release."""
        if not file.attestations:
            return None

        provenance_file = self.storage.get(f"{file.path}.provenance")
        return hashlib.file_digest(provenance_file, "sha256").hexdigest()

    def _persist_attestations(
        self, attestations: list[Attestation], file: File
    ) -> None:
        for attestation in attestations:
            with tempfile.NamedTemporaryFile() as tmp_file:
                tmp_file.write(attestation.model_dump_json().encode("utf-8"))

                attestation_digest = hashlib.file_digest(
                    tmp_file, "blake2b"
                ).hexdigest()
                database_attestation = DatabaseAttestation(
                    file=file, attestation_file_blake2_digest=attestation_digest
                )
                self.db.add(database_attestation)

                self.storage.store(
                    database_attestation.attestation_path,
                    tmp_file.name,
                    meta=None,
                )

    def _build_provenance_object(
        self, oidc_publisher: OIDCPublisher, attestations: list[Attestation]
    ) -> Provenance | None:
        try:
            publisher: Publisher = _publisher_from_oidc_publisher(oidc_publisher)
        except UnsupportedPublisherError:
            sentry_sdk.capture_message(
                f"Unsupported OIDCPublisher found {oidc_publisher.publisher_name}"
            )

            return None

        attestation_bundle = AttestationBundle(
            publisher=publisher,
            attestations=attestations,
        )

        return Provenance(attestation_bundles=[attestation_bundle])

    def _persist_provenance(
        self,
        provenance: Provenance,
        file: File,
    ) -> None:
        """
        Persist a Provenance object in storage.
        """
        provenance_file_path = Path(f"{file.path}.provenance")
        with tempfile.NamedTemporaryFile() as f:
            f.write(provenance.model_dump_json().encode("utf-8"))
            f.flush()

            self.storage.store(
                provenance_file_path,
                f.name,
            )
