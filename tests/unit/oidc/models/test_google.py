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

from warehouse.oidc.models import _core, google


class TestGooglePublisher:
    def test_google_publisher_all_known_claims(self):
        assert google.GooglePublisher.all_known_claims() == {
            # verifiable claims
            "email",
            "email_verified",
            # optional verifiable claims
            "sub",
            # preverified claims
            "iss",
            "iat",
            "nbf",
            "exp",
            "aud",
            # unchecked claims
            "azp",
            "google",
        }

    def test_google_publisher_unaccounted_claims(self, monkeypatch):
        publisher = google.GooglePublisher(
            sub="fakesubject",
            email="fake@example.com",
        )

        scope = pretend.stub()
        sentry_sdk = pretend.stub(
            capture_message=pretend.call_recorder(lambda s: None),
            push_scope=pretend.call_recorder(
                lambda: pretend.stub(
                    __enter__=lambda *a: scope, __exit__=lambda *a: None
                )
            ),
        )
        monkeypatch.setattr(_core, "sentry_sdk", sentry_sdk)

        # We don't care if these actually verify, only that they're present.
        signed_claims = {
            claim_name: "fake"
            for claim_name in google.GooglePublisher.all_known_claims()
        }
        signed_claims["fake-claim"] = "fake"
        signed_claims["another-fake-claim"] = "also-fake"
        assert not publisher.verify_claims(signed_claims=signed_claims)
        assert sentry_sdk.capture_message.calls == [
            pretend.call(
                "JWT for GooglePublisher has unaccounted claims: "
                "['another-fake-claim', 'fake-claim']"
            )
        ]
        assert scope.fingerprint == ["another-fake-claim", "fake-claim"]

    def test_google_publisher_missing_claims(self, monkeypatch):
        publisher = google.GooglePublisher(
            sub="fakesubject",
            email="fake@example.com",
        )

        scope = pretend.stub()
        sentry_sdk = pretend.stub(
            capture_message=pretend.call_recorder(lambda s: None),
            push_scope=pretend.call_recorder(
                lambda: pretend.stub(
                    __enter__=lambda *a: scope, __exit__=lambda *a: None
                )
            ),
        )
        monkeypatch.setattr(_core, "sentry_sdk", sentry_sdk)

        signed_claims = {
            claim_name: "fake"
            for claim_name in google.GooglePublisher.all_known_claims()
        }
        # Pop the first signed claim, so that it's the first one to fail.
        signed_claims.pop("email")
        assert "email" not in signed_claims
        assert publisher.__required_verifiable_claims__
        assert not publisher.verify_claims(signed_claims=signed_claims)
        assert sentry_sdk.capture_message.calls == [
            pretend.call("JWT for GooglePublisher is missing claim: email")
        ]
        assert scope.fingerprint == ["email"]

    @pytest.mark.parametrize(
        ("email_verified", "valid"),
        [(False, False), ("truthy-but-not-bool", False), ("", False), (True, True)],
    )
    def test_google_publisher_email_verified(self, email_verified, valid):
        publisher = google.GooglePublisher(
            sub="fakesubject",
            email="fake@example.com",
        )

        signed_claims = {
            "sub": "fakesubject",
            "email": "fake@example.com",
            "email_verified": email_verified,
        }
        assert publisher.verify_claims(signed_claims=signed_claims) is valid
