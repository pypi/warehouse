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
from warehouse.attestations.interfaces import IReleaseVerificationService
from warehouse.attestations.models import Attestation as DatabaseAttestation
from warehouse.metrics.interfaces import IMetricsService
from warehouse.oidc.models import (
    GitHubPublisher as GitHubOIDCPublisher,
    GitLabPublisher as GitLabOIDCPublisher,
    OIDCPublisher,
)
from warehouse.packaging.interfaces import IFileStorage
from warehouse.packaging.models import File


def _publisher_from_oidc_publisher(publisher: OIDCPublisher) -> Publisher:
    """
    Convert an OIDCPublisher object in a pypy-attestations Publisher.
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


@implementer(IReleaseVerificationService)
class ReleaseVerificationService:

    def __init__(
        self,
        storage: IFileStorage,
        metrics: IMetricsService,
    ):
        self.storage: IFileStorage = storage
        self.metrics: IMetricsService = metrics

    @classmethod
    def create_service(cls, _context, request: Request):
        return cls(
            storage=request.find_service(IFileStorage),
            metrics=request.find_service(IMetricsService),
        )

    def persist_attestations(self, attestations: list[Attestation], file: File) -> None:
        for attestation in attestations:
            with tempfile.NamedTemporaryFile() as tmp_file:
                tmp_file.write(attestation.model_dump_json().encode("utf-8"))

                attestation_digest = hashlib.file_digest(
                    tmp_file, "blake2b"
                ).hexdigest()
                database_attestation = DatabaseAttestation(
                    file=file, attestation_file_blake2_digest=attestation_digest
                )

                self.storage.store(
                    database_attestation.attestation_path,
                    tmp_file.name,
                    meta=None,
                )

            file.attestations.append(database_attestation)

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

        Warning, attestation data at the beginning of this function is untrusted.
        """
        publisher: OIDCPublisher | None = request.oidc_publisher
        if not publisher or not publisher.publisher_name == "GitHub":
            raise AttestationUploadError(
                "Attestations are only supported when using Trusted "
                "Publishing with GitHub Actions.",
            )

        try:
            attestations = TypeAdapter(list[Attestation]).validate_json(
                request.POST["attestations"]
            )
        except ValidationError as e:
            # Log invalid (malformed) attestation upload
            self.metrics.increment("warehouse.upload.attestations.malformed")
            raise AttestationUploadError(
                f"Error while decoding the included attestation: {e}",
            )

        if len(attestations) > 1:
            self.metrics.increment(
                "warehouse.upload.attestations.failed_multiple_attestations"
            )

            raise AttestationUploadError(
                "Only a single attestation per file is supported.",
            )

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

    def generate_and_store_provenance_file(
        self, oidc_publisher: OIDCPublisher, file: File, attestations: list[Attestation]
    ) -> None:
        try:
            publisher: Publisher = _publisher_from_oidc_publisher(oidc_publisher)
        except UnsupportedPublisherError:
            sentry_sdk.capture_message(
                f"Unsupported OIDCPublisher found {oidc_publisher.publisher_name}"
            )

            return

        attestation_bundle = AttestationBundle(
            publisher=publisher,
            attestations=attestations,
        )

        provenance = Provenance(attestation_bundles=[attestation_bundle])

        provenance_file_path = Path(f"{file.path}.provenance")
        with tempfile.NamedTemporaryFile() as f:
            f.write(provenance.model_dump_json().encode("utf-8"))
            f.flush()

            self.storage.store(
                provenance_file_path,
                f.name,
            )

    def get_provenance_digest(self, file: File) -> str | None:
        """Returns the sha256 digest of the provenance file for the release."""
        if not file.attestations or not file.publisher_url:
            return None

        provenance_file = self.storage.get(f"{file.path}.provenance")
        return hashlib.file_digest(provenance_file, "sha256").hexdigest()
