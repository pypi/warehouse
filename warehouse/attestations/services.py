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

import sentry_sdk

from pydantic import TypeAdapter, ValidationError
from pypi_attestations import (
    Attestation,
    AttestationType,
    Distribution,
    VerificationError,
)
from sigstore.verify import Verifier
from zope.interface import implementer

from warehouse.attestations.errors import AttestationUploadError
from warehouse.attestations.interfaces import IAttestationsService
from warehouse.attestations.models import Attestation as DatabaseAttestation
from warehouse.metrics.interfaces import IMetricsService
from warehouse.oidc.interfaces import SignedClaims
from warehouse.oidc.models import OIDCPublisher
from warehouse.packaging.interfaces import IFileStorage
from warehouse.packaging.models import File


@implementer(IAttestationsService)
class AttestationsService:

    def __init__(
        self,
        storage: IFileStorage,
        metrics: IMetricsService,
        publisher: OIDCPublisher,
        claims: SignedClaims,
    ):
        self.storage: IFileStorage = storage
        self.metrics: IMetricsService = metrics

        self.publisher: OIDCPublisher = publisher
        self.claims: SignedClaims = claims

    @classmethod
    def create_service(cls, _context, request):
        return cls(
            storage=request.find_service(IFileStorage),
            metrics=request.find_service(IMetricsService),
            claims=request.oidc_claims,
            publisher=request.oidc_publisher,
        )

    def persist(
        self, attestations: list[Attestation], file: File
    ) -> list[DatabaseAttestation]:
        attestations_db_models = []
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

                attestations_db_models.append(database_attestation)

        return attestations_db_models

    def parse(self, attestation_data, distribution: Distribution) -> list[Attestation]:
        """
        Process any attestations included in a file upload request

        Attestations, if present, will be parsed and verified against the uploaded
        artifact. Attestations are only allowed when uploading via a Trusted
        Publisher, because a Trusted Publisher provides the identity that will be
        used to verify the attestations.
        Only GitHub Actions Trusted Publishers are supported.

        Warning, attestation data at the beginning of this function is untrusted.
        """
        if not self.publisher or not self.publisher.publisher_name == "GitHub":
            raise AttestationUploadError(
                "Attestations are only supported when using Trusted "
                "Publishing with GitHub Actions.",
            )

        try:
            attestations = TypeAdapter(list[Attestation]).validate_json(
                attestation_data
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

        verification_policy = self.publisher.publisher_verification_policy(self.claims)
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
