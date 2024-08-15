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

import pretend
import pytest

from pydantic import TypeAdapter
from pypi_attestations import (
    Attestation,
    AttestationType,
    Envelope,
    VerificationError,
    VerificationMaterial,
)
from sigstore.verify import Verifier
from zope.interface.verify import verifyClass

from tests.common.db.packaging import FileFactory
from warehouse.attestations.errors import AttestationUploadError
from warehouse.attestations.interfaces import IAttestationsService
from warehouse.attestations.services import AttestationsService
from warehouse.metrics import IMetricsService
from warehouse.packaging import IFileStorage

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
        assert verifyClass(IAttestationsService, AttestationsService)

    def test_create_service(self):
        claims = {"claim": "fake"}
        request = pretend.stub(
            find_service=pretend.call_recorder(
                lambda svc, context=None, name=None: {
                    # IFileStorage: user_service,
                    # IMetricsService: sender,
                }.get(svc)
            ),
            oidc_claims=claims,
            oidc_publisher=pretend.stub(),
        )

        service = AttestationsService.create_service(None, request)
        assert not set(request.find_service.calls) ^ {
            pretend.call(IFileStorage),
            pretend.call(IMetricsService),
        }

        assert service.claims == claims

    def test_persist(self, db_request):
        @pretend.call_recorder
        def storage_service_store(path: str, file_path, *_args, **_kwargs):
            expected = VALID_ATTESTATION.model_dump_json().encode("utf-8")
            with open(file_path, "rb") as fp:
                assert fp.read() == expected

            assert path.endswith(".attestation")

        attestations_service = AttestationsService(
            storage=pretend.stub(
                store=storage_service_store,
            ),
            metrics=pretend.stub(),
            publisher=pretend.stub(),
            claims=pretend.stub(),
        )

        attestations_service.persist([VALID_ATTESTATION], FileFactory.create())

    def test_parse_no_publisher(self):
        attestations_service = AttestationsService(
            storage=pretend.stub(),
            metrics=pretend.stub(),
            publisher=None,
            claims=pretend.stub(),
        )

        with pytest.raises(
            AttestationUploadError,
            match="Attestations are only supported when using Trusted",
        ):
            attestations_service.parse(pretend.stub(), pretend.stub())

    def test_parse_unsupported_publisher(self):
        attestations_service = AttestationsService(
            storage=pretend.stub(),
            metrics=pretend.stub(),
            publisher=pretend.stub(publisher_name="fake-publisher"),
            claims=pretend.stub(),
        )

        with pytest.raises(
            AttestationUploadError,
            match="Attestations are only supported when using Trusted",
        ):
            attestations_service.parse(pretend.stub(), pretend.stub())

    def test_parse_malformed_attestation(self, metrics):
        attestations_service = AttestationsService(
            storage=pretend.stub(),
            metrics=metrics,
            publisher=pretend.stub(publisher_name="GitHub"),
            claims=pretend.stub(),
        )

        with pytest.raises(
            AttestationUploadError,
            match="Error while decoding the included attestation",
        ):
            attestations_service.parse({"malformed-attestation"}, pretend.stub())

        assert (
            pretend.call("warehouse.upload.attestations.malformed")
            in metrics.increment.calls
        )

    def test_parse_multiple_attestations(self, metrics):
        attestations_service = AttestationsService(
            storage=pretend.stub(),
            metrics=metrics,
            publisher=pretend.stub(
                publisher_name="GitHub",
            ),
            claims=pretend.stub(),
        )

        with pytest.raises(
            AttestationUploadError, match="Only a single attestation per file"
        ):
            attestations_service.parse(
                TypeAdapter(list[Attestation]).dump_json(
                    [VALID_ATTESTATION, VALID_ATTESTATION]
                ),
                pretend.stub(),
            )

        assert (
            pretend.call("warehouse.upload.attestations.failed_multiple_attestations")
            in metrics.increment.calls
        )

    @pytest.mark.parametrize(
        "verify_exception, expected_message",
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
        self, metrics, monkeypatch, verify_exception, expected_message
    ):
        attestations_service = AttestationsService(
            storage=pretend.stub(),
            metrics=metrics,
            publisher=pretend.stub(
                publisher_name="GitHub",
                publisher_verification_policy=pretend.call_recorder(lambda c: None),
            ),
            claims=pretend.stub(),
        )

        def failing_verify(_self, _verifier, _policy, _dist):
            raise verify_exception("error")

        monkeypatch.setattr(Verifier, "production", lambda: pretend.stub())
        monkeypatch.setattr(Attestation, "verify", failing_verify)

        with pytest.raises(AttestationUploadError, match=expected_message):
            attestations_service.parse(
                TypeAdapter(list[Attestation]).dump_json([VALID_ATTESTATION]),
                pretend.stub(),
            )

    def test_parse_wrong_predicate(self, metrics, monkeypatch):
        attestations_service = AttestationsService(
            storage=pretend.stub(),
            metrics=metrics,
            publisher=pretend.stub(
                publisher_name="GitHub",
                publisher_verification_policy=pretend.call_recorder(lambda c: None),
            ),
            claims=pretend.stub(),
        )

        monkeypatch.setattr(Verifier, "production", lambda: pretend.stub())
        monkeypatch.setattr(
            Attestation, "verify", lambda *args: ("wrong-predicate", {})
        )

        with pytest.raises(
            AttestationUploadError, match="Attestation with unsupported predicate"
        ):
            attestations_service.parse(
                TypeAdapter(list[Attestation]).dump_json([VALID_ATTESTATION]),
                pretend.stub(),
            )

        assert (
            pretend.call(
                "warehouse.upload.attestations.failed_unsupported_predicate_type"
            )
            in metrics.increment.calls
        )

    def test_parse_succeed(self, metrics, monkeypatch):
        attestations_service = AttestationsService(
            storage=pretend.stub(),
            metrics=metrics,
            publisher=pretend.stub(
                publisher_name="GitHub",
                publisher_verification_policy=pretend.call_recorder(lambda c: None),
            ),
            claims=pretend.stub(),
        )

        monkeypatch.setattr(Verifier, "production", lambda: pretend.stub())
        monkeypatch.setattr(
            Attestation, "verify", lambda *args: (AttestationType.PYPI_PUBLISH_V1, {})
        )

        attestations = attestations_service.parse(
            TypeAdapter(list[Attestation]).dump_json([VALID_ATTESTATION]),
            pretend.stub(),
        )
        assert attestations == [VALID_ATTESTATION]
