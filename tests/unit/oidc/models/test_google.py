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

from tests.common.db.oidc import GooglePublisherFactory, PendingGooglePublisherFactory
from warehouse.oidc import errors
from warehouse.oidc.models import _core, google


def test_lookup_strategies():
    assert (
        len(google.GooglePublisher.__lookup_strategies__)
        == len(google.PendingGooglePublisher.__lookup_strategies__)
        == 2
    )


class TestGooglePublisher:
    def test_publisher_name(self):
        publisher = google.GooglePublisher(email="fake@example.com")

        assert publisher.publisher_name == "Google"

    def test_publisher_base_url(self):
        publisher = google.GooglePublisher(email="fake@example.com")

        assert publisher.publisher_base_url is None

    def test_publisher_url(self):
        publisher = google.GooglePublisher(email="fake@example.com")

        assert publisher.publisher_url() is None

    def test_stored_claims(self):
        publisher = google.GooglePublisher(email="fake@example.com")

        assert publisher.stored_claims() == {}

    def test_stringifies_as_email(self):
        publisher = google.GooglePublisher(email="fake@example.com")

        assert str(publisher) == publisher.email

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
        with pytest.raises(errors.InvalidPublisherError) as e:
            publisher.verify_claims(signed_claims=signed_claims)
        assert str(e.value) == "Check failed for required claim 'email'"
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
        with pytest.raises(errors.InvalidPublisherError) as e:
            publisher.verify_claims(signed_claims=signed_claims)
        assert str(e.value) == "Missing claim 'email'"
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
        if valid:
            # Does not raise
            publisher.verify_claims(signed_claims=signed_claims)
        else:
            with pytest.raises(errors.InvalidPublisherError) as e:
                publisher.verify_claims(signed_claims=signed_claims)
            assert str(e.value) == "Check failed for required claim 'email_verified'"

    @pytest.mark.parametrize(
        ("expected_sub", "actual_sub", "valid"),
        [
            # Both present: must match.
            ("fakesubject", "fakesubject", True),
            ("fakesubject", "wrongsubject", False),
            # Publisher configured without subject: any subject is acceptable.
            ("", "anysubject", True),
            # Publisher configured with subject, none provided: must fail.
            ("fakesubject", None, False),
        ],
    )
    def test_google_publisher_sub_is_optional(self, expected_sub, actual_sub, valid):
        publisher = google.GooglePublisher(
            sub=expected_sub,
            email="fake@example.com",
        )

        signed_claims = {
            "sub": actual_sub,
            "email": "fake@example.com",
            "email_verified": True,
        }
        if valid:
            # Does not raise
            publisher.verify_claims(signed_claims=signed_claims)
        else:
            with pytest.raises(errors.InvalidPublisherError) as e:
                publisher.verify_claims(signed_claims=signed_claims)
            assert str(e.value) == "Check failed for optional claim 'sub'"


class TestPendingGooglePublisher:
    @pytest.mark.parametrize("sub", ["fakesubject", None])
    def test_reify_does_not_exist_yet(self, db_request, sub):
        pending_publisher = PendingGooglePublisherFactory.create(sub=sub)
        assert (
            db_request.db.query(google.GooglePublisher)
            .filter_by(
                email=pending_publisher.email,
                sub=pending_publisher.sub,
            )
            .one_or_none()
            is None
        )
        publisher = pending_publisher.reify(db_request.db)

        # If an OIDC publisher for this pending publisher does not already exist,
        # a new one is created and the pending publisher is marked for deletion.
        assert isinstance(publisher, google.GooglePublisher)
        assert pending_publisher in db_request.db.deleted
        assert publisher.email == pending_publisher.email
        assert publisher.sub == pending_publisher.sub

    @pytest.mark.parametrize("sub", ["fakesubject", None])
    def test_reify_already_exists(self, db_request, sub):
        existing_publisher = GooglePublisherFactory.create(sub=sub)
        pending_publisher = PendingGooglePublisherFactory.create(
            email=existing_publisher.email,
            sub=existing_publisher.sub,
        )
        publisher = pending_publisher.reify(db_request.db)

        # If an OIDC publisher for this pending publisher already exists,
        # it is returned and the pending publisher is marked for deletion.
        assert existing_publisher == publisher
        assert pending_publisher in db_request.db.deleted
