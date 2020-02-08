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

import collections
import datetime
import json
import uuid

import freezegun
import pretend
import pytest
import requests

from zope.interface.verify import verifyClass

import warehouse.utils.otp as otp
import warehouse.utils.webauthn as webauthn

from warehouse.accounts import services
from warehouse.accounts.interfaces import (
    IGitHubTokenScanningPayloadVerifyService,
    IPasswordBreachedService,
    ITokenService,
    IUserService,
    TokenExpired,
    TokenInvalid,
    TokenMissing,
    TooManyEmailsAdded,
    TooManyFailedLogins,
)
from warehouse.accounts.models import DisableReason
from warehouse.metrics import IMetricsService, NullMetrics
from warehouse.rate_limiting.interfaces import IRateLimiter

from ...common.db.accounts import EmailFactory, UserFactory


class TestDatabaseUserService:
    def test_verify_service(self):
        assert verifyClass(IUserService, services.DatabaseUserService)

    def test_service_creation(self, monkeypatch):
        crypt_context_obj = pretend.stub()
        crypt_context_cls = pretend.call_recorder(lambda **kwargs: crypt_context_obj)
        monkeypatch.setattr(services, "CryptContext", crypt_context_cls)

        session = pretend.stub()
        service = services.DatabaseUserService(session, metrics=NullMetrics())

        assert service.db is session
        assert service.hasher is crypt_context_obj
        assert crypt_context_cls.calls == [
            pretend.call(
                schemes=[
                    "argon2",
                    "bcrypt_sha256",
                    "bcrypt",
                    "django_bcrypt",
                    "unix_disabled",
                ],
                deprecated=["auto"],
                truncate_error=True,
                argon2__memory_cost=1024,
                argon2__parallelism=6,
                argon2__time_cost=6,
            )
        ]

    def test_service_creation_ratelimiters(self, monkeypatch):
        crypt_context_obj = pretend.stub()
        crypt_context_cls = pretend.call_recorder(lambda **kwargs: crypt_context_obj)
        monkeypatch.setattr(services, "CryptContext", crypt_context_cls)

        ratelimiters = {"user.login": pretend.stub(), "global.login": pretend.stub()}

        session = pretend.stub()
        service = services.DatabaseUserService(
            session, metrics=NullMetrics(), ratelimiters=ratelimiters
        )

        assert service.db is session
        assert service.ratelimiters == ratelimiters
        assert service.hasher is crypt_context_obj
        assert crypt_context_cls.calls == [
            pretend.call(
                schemes=[
                    "argon2",
                    "bcrypt_sha256",
                    "bcrypt",
                    "django_bcrypt",
                    "unix_disabled",
                ],
                deprecated=["auto"],
                truncate_error=True,
                argon2__memory_cost=1024,
                argon2__parallelism=6,
                argon2__time_cost=6,
            )
        ]

    def test_find_userid_nonexistent_user(self, user_service):
        assert user_service.find_userid("my_username") is None

    def test_find_userid_existing_user(self, user_service):
        user = UserFactory.create()
        assert user_service.find_userid(user.username) == user.id

    def test_check_password_global_rate_limited(self, user_service, metrics):
        resets = pretend.stub()
        limiter = pretend.stub(test=lambda: False, resets_in=lambda: resets)
        user_service.ratelimiters["global.login"] = limiter

        with pytest.raises(TooManyFailedLogins) as excinfo:
            user_service.check_password(uuid.uuid4(), None, tags=["foo"])

        assert excinfo.value.resets_in is resets
        assert metrics.increment.calls == [
            pretend.call("warehouse.authentication.start", tags=["foo"]),
            pretend.call(
                "warehouse.authentication.ratelimited",
                tags=["foo", "ratelimiter:global"],
            ),
        ]

    def test_check_password_nonexistent_user(self, user_service, metrics):
        assert not user_service.check_password(uuid.uuid4(), None, tags=["foo"])
        assert metrics.increment.calls == [
            pretend.call("warehouse.authentication.start", tags=["foo"]),
            pretend.call(
                "warehouse.authentication.failure", tags=["foo", "failure_reason:user"]
            ),
        ]

    def test_check_password_user_rate_limited(self, user_service, metrics):
        user = UserFactory.create()
        resets = pretend.stub()
        limiter = pretend.stub(
            test=pretend.call_recorder(lambda uid: False),
            resets_in=pretend.call_recorder(lambda uid: resets),
        )
        user_service.ratelimiters["user.login"] = limiter

        with pytest.raises(TooManyFailedLogins) as excinfo:
            user_service.check_password(user.id, None)

        assert excinfo.value.resets_in is resets
        assert limiter.test.calls == [pretend.call(user.id)]
        assert limiter.resets_in.calls == [pretend.call(user.id)]
        assert metrics.increment.calls == [
            pretend.call("warehouse.authentication.start", tags=[]),
            pretend.call(
                "warehouse.authentication.ratelimited", tags=["ratelimiter:user"]
            ),
        ]

    def test_check_password_invalid(self, user_service, metrics):
        user = UserFactory.create()
        user_service.hasher = pretend.stub(
            verify_and_update=pretend.call_recorder(lambda l, r: (False, None))
        )

        assert not user_service.check_password(user.id, "user password")
        assert user_service.hasher.verify_and_update.calls == [
            pretend.call("user password", user.password)
        ]
        assert metrics.increment.calls == [
            pretend.call("warehouse.authentication.start", tags=[]),
            pretend.call(
                "warehouse.authentication.failure", tags=["failure_reason:password"]
            ),
        ]

    def test_check_password_valid(self, user_service, metrics):
        user = UserFactory.create()
        user_service.hasher = pretend.stub(
            verify_and_update=pretend.call_recorder(lambda l, r: (True, None))
        )

        assert user_service.check_password(user.id, "user password", tags=["bar"])
        assert user_service.hasher.verify_and_update.calls == [
            pretend.call("user password", user.password)
        ]
        assert metrics.increment.calls == [
            pretend.call("warehouse.authentication.start", tags=["bar"]),
            pretend.call("warehouse.authentication.ok", tags=["bar"]),
        ]

    def test_check_password_updates(self, user_service):
        user = UserFactory.create()
        password = user.password
        user_service.hasher = pretend.stub(
            verify_and_update=pretend.call_recorder(lambda l, r: (True, "new password"))
        )

        assert user_service.check_password(user.id, "user password")
        assert user_service.hasher.verify_and_update.calls == [
            pretend.call("user password", password)
        ]
        assert user.password == "new password"

    def test_create_user(self, user_service):
        user = UserFactory.build()
        new_user = user_service.create_user(
            username=user.username, name=user.name, password=user.password
        )
        user_service.db.flush()
        user_from_db = user_service.get_user(new_user.id)

        assert user_from_db.username == user.username
        assert user_from_db.name == user.name
        assert not user_from_db.is_active
        assert not user_from_db.is_superuser

    def test_add_email_not_primary(self, user_service):
        user = UserFactory.create()
        email = "foo@example.com"
        new_email = user_service.add_email(user.id, email, "0.0.0.0", primary=False)

        assert new_email.email == email
        assert new_email.user == user
        assert not new_email.primary
        assert not new_email.verified

    def test_add_email_defaults_to_primary(self, user_service):
        user = UserFactory.create()
        email1 = "foo@example.com"
        email2 = "bar@example.com"
        new_email1 = user_service.add_email(user.id, email1, "0.0.0.0")
        new_email2 = user_service.add_email(user.id, email2, "0.0.0.0")

        assert new_email1.email == email1
        assert new_email1.user == user
        assert new_email1.primary
        assert not new_email1.verified

        assert new_email2.email == email2
        assert new_email2.user == user
        assert not new_email2.primary
        assert not new_email2.verified

    def test_add_email_rate_limited(self, user_service, metrics):
        resets = pretend.stub()
        limiter = pretend.stub(
            hit=pretend.call_recorder(lambda ip: None),
            test=pretend.call_recorder(lambda ip: False),
            resets_in=pretend.call_recorder(lambda ip: resets),
        )
        user_service.ratelimiters["email.add"] = limiter

        user = UserFactory.build()

        with pytest.raises(TooManyEmailsAdded) as excinfo:
            user_service.add_email(user.id, user.email, "0.0.0.0")

        assert excinfo.value.resets_in is resets
        assert limiter.test.calls == [pretend.call("0.0.0.0")]
        assert limiter.resets_in.calls == [pretend.call("0.0.0.0")]
        assert metrics.increment.calls == [
            pretend.call(
                "warehouse.email.add.ratelimited", tags=["ratelimiter:email.add"]
            )
        ]

    def test_update_user(self, user_service):
        user = UserFactory.create()
        new_name, password = "new username", "TestPa@@w0rd"
        user_service.update_user(user.id, username=new_name, password=password)
        user_from_db = user_service.get_user(user.id)
        assert user_from_db.username == user.username
        assert password != user_from_db.password
        assert user_service.hasher.verify(password, user_from_db.password)

    def test_update_user_without_pw(self, user_service):
        user = UserFactory.create()
        new_name = "new username"
        user_service.update_user(user.id, username=new_name)
        user_from_db = user_service.get_user(user.id)
        assert user_from_db.username == user.username

    def test_find_by_email(self, user_service):
        user = UserFactory.create()
        EmailFactory.create(user=user, primary=True, verified=False)

        found_userid = user_service.find_userid_by_email(user.emails[0].email)
        user_service.db.flush()

        assert user.id == found_userid

    def test_find_by_email_not_found(self, user_service):
        assert user_service.find_userid_by_email("something") is None

    def test_create_login_success(self, user_service):
        user = user_service.create_user("test_user", "test_name", "test_password")

        assert user.id is not None
        # now make sure that we can log in as that user
        assert user_service.check_password(user.id, "test_password")

    def test_create_login_error(self, user_service):
        user = user_service.create_user("test_user", "test_name", "test_password")

        assert user.id is not None
        assert not user_service.check_password(user.id, "bad_password")

    def test_get_user_by_username(self, user_service):
        user = UserFactory.create()
        found_user = user_service.get_user_by_username(user.username)
        user_service.db.flush()

        assert user.username == found_user.username

    def test_get_user_by_username_failure(self, user_service):
        UserFactory.create()
        found_user = user_service.get_user_by_username("UNKNOWNTOTHEWORLD")
        user_service.db.flush()

        assert found_user is None

    def test_get_user_by_email(self, user_service):
        user = UserFactory.create()
        EmailFactory.create(user=user, primary=True, verified=False)
        found_user = user_service.get_user_by_email(user.emails[0].email)
        user_service.db.flush()

        assert user.id == found_user.id

    def test_get_user_by_email_failure(self, user_service):
        found_user = user_service.get_user_by_email("example@email.com")
        user_service.db.flush()

        assert found_user is None

    def test_disable_password(self, user_service):
        user = UserFactory.create()

        # Need to give the user a good password first.
        user_service.update_user(user.id, password="foo")
        assert user.password != "!"

        # Now we'll actually test our disable function.
        user_service.disable_password(user.id)
        assert user.password == "!"

    @pytest.mark.parametrize(
        ("disabled", "reason"),
        [(True, None), (True, DisableReason.CompromisedPassword), (False, None)],
    )
    def test_is_disabled(self, user_service, disabled, reason):
        user = UserFactory.create()
        user_service.update_user(user.id, password="foo")
        if disabled:
            user_service.disable_password(user.id, reason=reason)
        assert user_service.is_disabled(user.id) == (disabled, reason)

    def test_updating_password_undisables(self, user_service):
        user = UserFactory.create()
        user_service.disable_password(user.id, reason=DisableReason.CompromisedPassword)
        assert user_service.is_disabled(user.id) == (
            True,
            DisableReason.CompromisedPassword,
        )
        user_service.update_user(user.id, password="foo")
        assert user_service.is_disabled(user.id) == (False, None)

    def test_has_two_factor(self, user_service):
        user = UserFactory.create()
        assert not user_service.has_two_factor(user.id)

        user_service.update_user(user.id, totp_secret=b"foobar")
        assert user_service.has_two_factor(user.id)

    def test_has_totp(self, user_service):
        user = UserFactory.create()
        assert not user_service.has_totp(user.id)
        user_service.update_user(user.id, totp_secret=b"foobar")
        assert user_service.has_totp(user.id)

    def test_has_webauthn(self, user_service):
        user = UserFactory.create()
        assert not user_service.has_webauthn(user.id)
        user_service.add_webauthn(
            user.id,
            label="test_label",
            credential_id="foo",
            public_key="bar",
            sign_count=1,
        )
        assert user_service.has_webauthn(user.id)

    def test_get_last_totp_value(self, user_service):
        user = UserFactory.create()
        assert user_service.get_last_totp_value(user.id) is None

        user_service.update_user(user.id, last_totp_value="123456")
        assert user_service.get_last_totp_value(user.id) == "123456"

    @pytest.mark.parametrize(
        ("last_totp_value", "valid"),
        ([None, True], ["000000", True], ["000000", False]),
    )
    def test_check_totp_value(self, user_service, monkeypatch, last_totp_value, valid):
        verify_totp = pretend.call_recorder(lambda *a: valid)
        monkeypatch.setattr(otp, "verify_totp", verify_totp)

        user = UserFactory.create()
        user_service.update_user(
            user.id, last_totp_value=last_totp_value, totp_secret=b"foobar"
        )
        user_service.add_email(
            user.id, "foo@bar.com", "0.0.0.0", primary=True, verified=True
        )

        assert user_service.check_totp_value(user.id, b"123456") == valid

    def test_check_totp_value_reused(self, user_service):
        user = UserFactory.create()
        user_service.update_user(
            user.id, last_totp_value="123456", totp_secret=b"foobar"
        )

        assert not user_service.check_totp_value(user.id, b"123456")

    def test_check_totp_value_no_secret(self, user_service):
        user = UserFactory.create()
        assert not user_service.check_totp_value(user.id, b"123456")

    def test_check_totp_global_rate_limited(self, user_service, metrics):
        resets = pretend.stub()
        limiter = pretend.stub(test=lambda: False, resets_in=lambda: resets)
        user_service.ratelimiters["global.login"] = limiter

        with pytest.raises(TooManyFailedLogins) as excinfo:
            user_service.check_totp_value(uuid.uuid4(), b"123456", tags=["foo"])

        assert excinfo.value.resets_in is resets
        assert metrics.increment.calls == [
            pretend.call("warehouse.authentication.two_factor.start", tags=["foo"]),
            pretend.call(
                "warehouse.authentication.two_factor.ratelimited",
                tags=["foo", "ratelimiter:global"],
            ),
        ]

    def test_check_totp_value_user_rate_limited(self, user_service, metrics):
        user = UserFactory.create()
        resets = pretend.stub()
        limiter = pretend.stub(
            test=pretend.call_recorder(lambda uid: False),
            resets_in=pretend.call_recorder(lambda uid: resets),
        )
        user_service.ratelimiters["user.login"] = limiter

        with pytest.raises(TooManyFailedLogins) as excinfo:
            user_service.check_totp_value(user.id, b"123456")

        assert excinfo.value.resets_in is resets
        assert limiter.test.calls == [pretend.call(user.id)]
        assert limiter.resets_in.calls == [pretend.call(user.id)]
        assert metrics.increment.calls == [
            pretend.call("warehouse.authentication.two_factor.start", tags=[]),
            pretend.call(
                "warehouse.authentication.two_factor.ratelimited",
                tags=["ratelimiter:user"],
            ),
        ]

    def test_check_totp_value_invalid_secret(self, user_service):
        user = UserFactory.create()
        limiter = pretend.stub(
            hit=pretend.call_recorder(lambda *a, **kw: None), test=lambda *a, **kw: True
        )
        user_service.ratelimiters["user.login"] = limiter
        user_service.ratelimiters["global.login"] = limiter

        valid = user_service.check_totp_value(user.id, b"123456")

        assert not valid
        assert limiter.hit.calls == [pretend.call(user.id), pretend.call()]

    def test_check_totp_value_invalid_totp(self, user_service, monkeypatch):
        user = UserFactory.create()
        limiter = pretend.stub(
            hit=pretend.call_recorder(lambda *a, **kw: None), test=lambda *a, **kw: True
        )
        user_service.get_totp_secret = lambda uid: "secret"
        monkeypatch.setattr(otp, "verify_totp", lambda secret, value: False)
        user_service.ratelimiters["user.login"] = limiter
        user_service.ratelimiters["global.login"] = limiter

        valid = user_service.check_totp_value(user.id, b"123456")

        assert not valid
        assert limiter.hit.calls == [pretend.call(user.id), pretend.call()]

    @pytest.mark.parametrize(
        ("challenge", "rp_name", "rp_id"),
        (["fake_challenge", "fake_rp_name", "fake_rp_id"], [None, None, None]),
    )
    def test_get_webauthn_credential_options(
        self, user_service, challenge, rp_name, rp_id
    ):
        user = UserFactory.create()
        options = user_service.get_webauthn_credential_options(
            user.id, challenge=challenge, rp_name=rp_name, rp_id=rp_id
        )

        assert options["user"]["id"] == str(user.id)
        assert options["user"]["name"] == user.username
        assert options["user"]["displayName"] == user.name
        assert options["challenge"] == challenge
        assert options["rp"]["name"] == rp_name
        assert options["rp"]["id"] == rp_id
        assert "icon" not in options["user"]

    def test_get_webauthn_assertion_options(self, user_service):
        user = UserFactory.create()
        user_service.add_webauthn(
            user.id,
            label="test_label",
            credential_id="foo",
            public_key="bar",
            sign_count=1,
        )

        options = user_service.get_webauthn_assertion_options(
            user.id, challenge="fake_challenge", rp_id="fake_rp_id"
        )

        assert options["challenge"] == "fake_challenge"
        assert options["rpId"] == "fake_rp_id"
        assert options["allowCredentials"][0]["id"] == user.webauthn[0].credential_id

    def test_verify_webauthn_credential(self, user_service, monkeypatch):
        user = UserFactory.create()
        user_service.add_webauthn(
            user.id,
            label="test_label",
            credential_id="foo",
            public_key="bar",
            sign_count=1,
        )

        fake_validated_credential = pretend.stub(credential_id=b"bar")
        verify_registration_response = pretend.call_recorder(
            lambda *a, **kw: fake_validated_credential
        )
        monkeypatch.setattr(
            webauthn, "verify_registration_response", verify_registration_response
        )

        validated_credential = user_service.verify_webauthn_credential(
            pretend.stub(),
            challenge=pretend.stub(),
            rp_id=pretend.stub(),
            origin=pretend.stub(),
        )

        assert validated_credential is fake_validated_credential

    def test_verify_webauthn_credential_already_in_use(self, user_service, monkeypatch):
        user = UserFactory.create()
        user_service.add_webauthn(
            user.id,
            label="test_label",
            credential_id="foo",
            public_key="bar",
            sign_count=1,
        )

        fake_validated_credential = pretend.stub(credential_id=b"foo")
        verify_registration_response = pretend.call_recorder(
            lambda *a, **kw: fake_validated_credential
        )
        monkeypatch.setattr(
            webauthn, "verify_registration_response", verify_registration_response
        )

        with pytest.raises(webauthn.RegistrationRejectedException):
            user_service.verify_webauthn_credential(
                pretend.stub(),
                challenge=pretend.stub(),
                rp_id=pretend.stub(),
                origin=pretend.stub(),
            )

    def test_verify_webauthn_assertion(self, user_service, monkeypatch):
        user = UserFactory.create()
        user_service.add_webauthn(
            user.id,
            label="test_label",
            credential_id="foo",
            public_key="bar",
            sign_count=1,
        )

        verify_assertion_response = pretend.call_recorder(lambda *a, **kw: 2)
        monkeypatch.setattr(
            webauthn, "verify_assertion_response", verify_assertion_response
        )

        updated_sign_count = user_service.verify_webauthn_assertion(
            user.id,
            pretend.stub(),
            challenge=pretend.stub(),
            origin=pretend.stub(),
            rp_id=pretend.stub(),
        )
        assert updated_sign_count == 2

    def test_get_webauthn_by_label(self, user_service):
        user = UserFactory.create()
        user_service.add_webauthn(
            user.id,
            label="test_label",
            credential_id="foo",
            public_key="bar",
            sign_count=1,
        )

        webauthn = user_service.get_webauthn_by_label(user.id, "test_label")
        assert webauthn is not None
        assert webauthn.label == "test_label"

        webauthn = user_service.get_webauthn_by_label(user.id, "not_a_real_label")
        assert webauthn is None

        other_user = UserFactory.create()
        webauthn = user_service.get_webauthn_by_label(other_user.id, "test_label")
        assert webauthn is None

    def test_get_webauthn_by_credential_id(self, user_service):
        user = UserFactory.create()
        user_service.add_webauthn(
            user.id,
            label="foo",
            credential_id="test_credential_id",
            public_key="bar",
            sign_count=1,
        )

        webauthn = user_service.get_webauthn_by_credential_id(
            user.id, "test_credential_id"
        )
        assert webauthn is not None
        assert webauthn.credential_id == "test_credential_id"

        webauthn = user_service.get_webauthn_by_credential_id(
            user.id, "not_a_real_label"
        )
        assert webauthn is None

        other_user = UserFactory.create()
        webauthn = user_service.get_webauthn_by_credential_id(
            other_user.id, "test_credential_id"
        )
        assert webauthn is None

    def test_has_recovery_codes(self, user_service):
        user = UserFactory.create()
        assert not user_service.has_recovery_codes(user.id)
        user_service.generate_recovery_codes(user.id)
        assert user_service.has_recovery_codes(user.id)

    def test_get_recovery_codes(self, user_service):
        user = UserFactory.create()
        assert len(user_service.get_recovery_codes(user.id)) == 0
        user_service.generate_recovery_codes(user.id)
        assert len(user_service.get_recovery_codes(user.id)) == 8

    def test_generate_recovery_codes(self, user_service):
        user = UserFactory.create()

        assert not user_service.has_recovery_codes(user.id)
        assert len(user_service.get_recovery_codes(user.id)) == 0

        codes = user_service.generate_recovery_codes(user.id)
        assert len(codes) == 8
        assert len(user_service.get_recovery_codes(user.id)) == 8

    def test_check_recovery_code(self, user_service, metrics):
        user = UserFactory.create()
        assert not user_service.check_recovery_code(user.id, "no codes yet")

        codes = user_service.generate_recovery_codes(user.id)
        assert len(codes) == 8
        assert len(user_service.get_recovery_codes(user.id)) == 8
        assert user_service.check_recovery_code(user.id, codes[0])

        # Once used, the code should not be accepted again.
        assert len(user_service.get_recovery_codes(user.id)) == 7
        assert not user_service.check_recovery_code(user.id, codes[0])

        assert metrics.increment.calls == [
            pretend.call("warehouse.authentication.recovery_code.start"),
            pretend.call(
                "warehouse.authentication.recovery_code.failure",
                tags=["failure_reason:no_recovery_codes"],
            ),
            pretend.call("warehouse.authentication.recovery_code.start"),
            pretend.call("warehouse.authentication.recovery_code.ok"),
            pretend.call("warehouse.authentication.recovery_code.start"),
            pretend.call(
                "warehouse.authentication.recovery_code.failure",
                tags=["failure_reason:invalid_recovery_code"],
            ),
        ]

    def test_check_recovery_code_global_rate_limited(self, user_service, metrics):
        resets = pretend.stub()
        limiter = pretend.stub(test=lambda: False, resets_in=lambda: resets)
        user_service.ratelimiters["global.login"] = limiter

        with pytest.raises(TooManyFailedLogins) as excinfo:
            user_service.check_recovery_code(uuid.uuid4(), "recovery_code")

        assert excinfo.value.resets_in is resets
        assert metrics.increment.calls == [
            pretend.call("warehouse.authentication.recovery_code.start"),
            pretend.call(
                "warehouse.authentication.recovery_code.ratelimited",
                tags=["ratelimiter:global"],
            ),
        ]

    def test_check_recovery_code_user_rate_limited(self, user_service, metrics):
        user = UserFactory.create()
        resets = pretend.stub()
        limiter = pretend.stub(
            test=pretend.call_recorder(lambda uid: False),
            resets_in=pretend.call_recorder(lambda uid: resets),
        )
        user_service.ratelimiters["user.login"] = limiter

        with pytest.raises(TooManyFailedLogins) as excinfo:
            user_service.check_recovery_code(user.id, "recovery_code")

        assert excinfo.value.resets_in is resets
        assert limiter.test.calls == [pretend.call(user.id)]
        assert limiter.resets_in.calls == [pretend.call(user.id)]
        assert metrics.increment.calls == [
            pretend.call("warehouse.authentication.recovery_code.start"),
            pretend.call(
                "warehouse.authentication.recovery_code.ratelimited",
                tags=["ratelimiter:user"],
            ),
        ]

    def test_regenerate_recovery_codes(self, user_service):
        user = UserFactory.create()
        assert len(user_service.get_recovery_codes(user.id)) == 0
        user_service.generate_recovery_codes(user.id)
        initial_codes = user_service.get_recovery_codes(user.id)
        assert len(initial_codes) == 8
        user_service.generate_recovery_codes(user.id)
        new_codes = user_service.get_recovery_codes(user.id)
        assert len(new_codes) == 8
        assert [c.id for c in initial_codes] != [c.id for c in new_codes]


class TestTokenService:
    def test_verify_service(self):
        assert verifyClass(ITokenService, services.TokenService)

    def test_service_creation(self, monkeypatch):
        serializer_obj = pretend.stub()
        serializer_cls = pretend.call_recorder(lambda *a, **kw: serializer_obj)
        monkeypatch.setattr(services, "URLSafeTimedSerializer", serializer_cls)

        secret = pretend.stub()
        salt = pretend.stub()
        max_age = pretend.stub()
        service = services.TokenService(secret, salt, max_age)

        assert service.serializer == serializer_obj
        assert serializer_cls.calls == [pretend.call(secret, salt=salt)]

    def test_dumps(self, token_service):
        assert token_service.dumps({"foo": "bar"})

    def test_loads(self, token_service):
        token = token_service.dumps({"foo": "bar"})
        assert token_service.loads(token) == {"foo": "bar"}

    def test_loads_return_timestamp(self, token_service):
        sign_time = datetime.datetime.utcnow()
        with freezegun.freeze_time(sign_time):
            token = token_service.dumps({"foo": "bar"})

        assert token_service.loads(token, return_timestamp=True) == (
            {"foo": "bar"},
            sign_time.replace(microsecond=0),
        )

    @pytest.mark.parametrize("token", ["", None])
    def test_loads_token_is_none(self, token_service, token):
        with pytest.raises(TokenMissing):
            token_service.loads(token)

    def test_loads_token_is_expired(self, token_service):
        now = datetime.datetime.utcnow()

        with freezegun.freeze_time(now) as frozen_time:
            token = token_service.dumps({"foo": "bar"})

            frozen_time.tick(
                delta=datetime.timedelta(seconds=token_service.max_age + 1)
            )

            with pytest.raises(TokenExpired):
                token_service.loads(token)

    def test_loads_token_is_invalid(self, token_service):
        with pytest.raises(TokenInvalid):
            token_service.loads("invalid")


def test_database_login_factory(monkeypatch, pyramid_services, metrics):
    service_obj = pretend.stub()
    service_cls = pretend.call_recorder(
        lambda session, ratelimiters, metrics: service_obj
    )
    monkeypatch.setattr(services, "DatabaseUserService", service_cls)

    global_login_ratelimiter = pretend.stub()
    user_login_ratelimiter = pretend.stub()
    email_add_ratelimiter = pretend.stub()

    def find_service(iface, name=None, context=None):
        if iface != IRateLimiter and name is None:
            return pyramid_services.find_service(iface, context=context)

        assert iface is IRateLimiter
        assert context is None
        assert name in {"global.login", "user.login", "email.add"}

        return (
            {
                "global.login": global_login_ratelimiter,
                "user.login": user_login_ratelimiter,
                "email.add": email_add_ratelimiter,
            }
        ).get(name)

    context = pretend.stub()
    request = pretend.stub(db=pretend.stub(), find_service=find_service)

    assert services.database_login_factory(context, request) is service_obj
    assert service_cls.calls == [
        pretend.call(
            request.db,
            metrics=metrics,
            ratelimiters={
                "global.login": global_login_ratelimiter,
                "user.login": user_login_ratelimiter,
                "email.add": email_add_ratelimiter,
            },
        )
    ]


def test_token_service_factory_default_max_age(monkeypatch):
    name = "name"
    service_obj = pretend.stub()
    service_cls = pretend.call_recorder(lambda *args: service_obj)

    service_factory = services.TokenServiceFactory(name, service_cls)

    assert service_factory.name == name
    assert service_factory.service_class == service_cls

    context = pretend.stub()
    secret = pretend.stub()
    default_max_age = pretend.stub()
    request = pretend.stub(
        registry=pretend.stub(
            settings={
                "token.name.secret": secret,
                "token.default.max_age": default_max_age,
            }
        )
    )

    assert service_factory(context, request) is service_obj
    assert service_cls.calls == [pretend.call(secret, name, default_max_age)]


def test_token_service_factory_custom_max_age(monkeypatch):
    name = "name"
    service_obj = pretend.stub()
    service_cls = pretend.call_recorder(lambda *args: service_obj)

    service_factory = services.TokenServiceFactory(name, service_cls)

    assert service_factory.name == name
    assert service_factory.service_class == service_cls

    context = pretend.stub()
    secret = pretend.stub()
    default_max_age = pretend.stub()
    custom_max_age = pretend.stub()
    request = pretend.stub(
        registry=pretend.stub(
            settings={
                "token.name.secret": secret,
                "token.default.max_age": default_max_age,
                "token.name.max_age": custom_max_age,
            }
        )
    )

    assert service_factory(context, request) is service_obj
    assert service_cls.calls == [pretend.call(secret, name, custom_max_age)]


def test_token_service_factory_eq():
    assert services.TokenServiceFactory("foo") == services.TokenServiceFactory("foo")
    assert services.TokenServiceFactory("foo") != services.TokenServiceFactory("bar")
    assert services.TokenServiceFactory("foo") != object()


class TestHaveIBeenPwnedPasswordBreachedService:
    def test_verify_service(self):
        assert verifyClass(
            IPasswordBreachedService, services.HaveIBeenPwnedPasswordBreachedService
        )

    @pytest.mark.parametrize(
        ("password", "prefix", "expected", "dataset"),
        [
            (
                "password",
                "5baa6",
                True,
                (
                    "1e4c9b93f3f0682250b6cf8331b7ee68fd8:5\r\n"
                    "a8ff7fcd473d321e0146afd9e26df395147:3"
                ),
            ),
            (
                "password",
                "5baa6",
                True,
                (
                    "1E4C9B93F3F0682250B6CF8331B7EE68FD8:5\r\n"
                    "A8FF7FCD473D321E0146AFD9E26DF395147:3"
                ),
            ),
            (
                "correct horse battery staple",
                "abf7a",
                False,
                (
                    "1e4c9b93f3f0682250b6cf8331b7ee68fd8:5\r\n"
                    "a8ff7fcd473d321e0146afd9e26df395147:3"
                ),
            ),
        ],
    )
    def test_success(self, password, prefix, expected, dataset):
        response = pretend.stub(text=dataset, raise_for_status=lambda: None)
        session = pretend.stub(get=pretend.call_recorder(lambda url: response))

        svc = services.HaveIBeenPwnedPasswordBreachedService(
            session=session, metrics=NullMetrics()
        )

        assert svc.check_password(password) == expected
        assert session.get.calls == [
            pretend.call(f"https://api.pwnedpasswords.com/range/{prefix}")
        ]

    def test_failure(self):
        class AnError(Exception):
            pass

        def raiser():
            raise AnError

        response = pretend.stub(raise_for_status=raiser)
        session = pretend.stub(get=lambda url: response)

        svc = services.HaveIBeenPwnedPasswordBreachedService(
            session=session, metrics=NullMetrics()
        )

        with pytest.raises(AnError):
            svc.check_password("my password")

    def test_http_failure(self):
        @pretend.call_recorder
        def raiser():
            raise requests.RequestException()

        response = pretend.stub(raise_for_status=raiser)
        session = pretend.stub(get=lambda url: response)

        svc = services.HaveIBeenPwnedPasswordBreachedService(
            session=session, metrics=NullMetrics()
        )
        assert not svc.check_password("my password")
        assert raiser.calls

    def test_metrics_increments(self):
        class Metrics:
            def __init__(self):
                self.values = collections.Counter()

            def increment(self, metric):
                self.values[metric] += 1

        metrics = Metrics()

        svc = services.HaveIBeenPwnedPasswordBreachedService(
            session=pretend.stub(), metrics=metrics
        )

        svc._metrics_increment("something")
        svc._metrics_increment("another_thing")
        svc._metrics_increment("something")

        assert metrics.values == {"something": 2, "another_thing": 1}

    def test_factory(self):
        context = pretend.stub()
        request = pretend.stub(
            http=pretend.stub(),
            find_service=lambda iface, context: {
                (IMetricsService, None): NullMetrics()
            }[(iface, context)],
            help_url=lambda _anchor=None: f"http://localhost/help/#{_anchor}",
        )
        svc = services.HaveIBeenPwnedPasswordBreachedService.create_service(
            context, request
        )

        assert svc._http is request.http
        assert isinstance(svc._metrics, NullMetrics)
        assert svc._help_url == "http://localhost/help/#compromised-password"

    @pytest.mark.parametrize(
        ("help_url", "expected"),
        [
            (
                None,
                (
                    "This password appears in a security breach or has "
                    "been compromised and cannot be used."
                ),
            ),
            (
                "http://localhost/help/#compromised-password",
                (
                    "This password appears in a security breach or has been "
                    "compromised and cannot be used. See "
                    '<a href="http://localhost/help/#compromised-password">'
                    "this FAQ entry</a> for more information."
                ),
            ),
        ],
    )
    def test_failure_message(self, help_url, expected):
        context = pretend.stub()
        request = pretend.stub(
            http=pretend.stub(),
            find_service=lambda iface, context: {
                (IMetricsService, None): NullMetrics()
            }[(iface, context)],
            help_url=lambda _anchor=None: help_url,
        )
        svc = services.HaveIBeenPwnedPasswordBreachedService.create_service(
            context, request
        )
        assert svc.failure_message == expected

    @pytest.mark.parametrize(
        ("help_url", "expected"),
        [
            (
                None,
                (
                    "This password appears in a security breach or has been "
                    "compromised and cannot be used."
                ),
            ),
            (
                "http://localhost/help/#compromised-password",
                (
                    "This password appears in a security breach or has been "
                    "compromised and cannot be used. See the FAQ entry at "
                    "http://localhost/help/#compromised-password for more information."
                ),
            ),
        ],
    )
    def test_failure_message_plain(self, help_url, expected):
        context = pretend.stub()
        request = pretend.stub(
            http=pretend.stub(),
            find_service=lambda iface, context: {
                (IMetricsService, None): NullMetrics()
            }[(iface, context)],
            help_url=lambda _anchor=None: help_url,
        )
        svc = services.HaveIBeenPwnedPasswordBreachedService.create_service(
            context, request
        )
        assert svc.failure_message_plain == expected


class TestNullPasswordBreachedService:
    def test_verify_service(self):
        assert verifyClass(
            IPasswordBreachedService, services.NullPasswordBreachedService
        )

    def test_check_password(self):
        svc = services.NullPasswordBreachedService()
        assert not svc.check_password("password")

    def test_factory(self):
        context = pretend.stub()
        request = pretend.stub()
        svc = services.NullPasswordBreachedService.create_service(context, request)

        assert isinstance(svc, services.NullPasswordBreachedService)
        assert not svc.check_password("hunter2")


class TestGitHubTokenScanningPayloadVerifyService:
    def test_verify_service(self):
        assert verifyClass(
            IGitHubTokenScanningPayloadVerifyService,
            services.GitHubTokenScanningPayloadVerifyService,
        )

    def test_create_service(self):
        metrics = pretend.stub()
        session = pretend.stub()
        context = pretend.stub()
        request = pretend.stub(
            find_service=lambda iface, context: metrics, http=session
        )

        svc = services.GitHubTokenScanningPayloadVerifyService.create_service(
            context=context, request=request
        )

        assert isinstance(svc, services.GitHubTokenScanningPayloadVerifyService)
        assert svc._session is session
        assert svc._metrics is metrics

    def test_verify(self):
        # Example taken from
        # https://gist.github.com/ewjoachim/7dde11c31d9686ed6b4431c3ca166da2
        meta_payload = {
            "public_keys": [
                {
                    "key_identifier": "90a421169f0a406205f1563a953312f0be898d3c"
                    "7b6c06b681aa86a874555f4a",
                    "key": "-----BEGIN PUBLIC KEY-----\n"
                    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE9MJJHnMfn2+H4xL4YaPDA4RpJqU"
                    "q\nkCmRCBnYERxZanmcpzQSXs1X/AljlKkbJ8qpVIW4clayyef9gWhFbNHWAA==\n"
                    "-----END PUBLIC KEY-----",
                    "is_current": True,
                }
            ]
        }
        response = pretend.stub(
            json=lambda: meta_payload, raise_for_status=lambda: None
        )
        session = pretend.stub(get=lambda *a, **k: response)
        metrics = pretend.stub(increment=pretend.call_recorder(lambda str: None))
        request = pretend.stub(
            find_service=lambda iface, context: metrics, http=session
        )
        svc = services.GitHubTokenScanningPayloadVerifyService.create_service(
            context=None, request=request
        )
        key_id = "90a421169f0a406205f1563a953312f0be898d3c7b6c06b681aa86a874555f4a"
        signature = (
            "MEQCIAfgjgz6Ou/3DXMYZBervz1TKCHFsvwMcbuJhNZse622AiAG86/"
            "cku2XdcmFWNHl2WSJi2fkE8t+auvB24eURaOd2A=="
        )

        payload = (
            '[{"type":"github_oauth_token","token":"cb4985f91f740272c0234202299'
            'f43808034d7f5","url":" https://github.com/github/faketestrepo/blob/'
            'b0dd59c0b500650cacd4551ca5989a6194001b10/production.env"}]'
        )
        assert svc.verify(payload=payload, key_id=key_id, signature=signature) is True
        assert metrics.increment.calls == [
            pretend.call("warehouse.token_leak.github.auth.success")
        ]

    def test_verify_error(self):
        metrics = pretend.stub(increment=pretend.call_recorder(lambda str: None))
        request = pretend.stub(
            find_service=lambda iface, context: metrics, http=pretend.stub()
        )
        svc = services.GitHubTokenScanningPayloadVerifyService.create_service(
            context=pretend.stub(), request=request
        )
        svc._retrieve_public_key_payload = pretend.raiser(
            services.InvalidTokenLeakRequest("Bla", "bla")
        )
        assert svc.verify(payload={}, key_id="a", signature="a") is False

        assert metrics.increment.calls == [
            pretend.call("warehouse.token_leak.github.auth.error.bla")
        ]

    def test_retrieve_public_key_payload(self):
        meta_payload = {
            "public_keys": [
                {
                    "key_identifier": "90a421169f0a406205f1563a953312f0be898d3c"
                    "7b6c06b681aa86a874555f4a",
                    "key": "-----BEGIN PUBLIC KEY-----\n"
                    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE9MJJHnMfn2+H4xL4YaPDA4RpJqU"
                    "q\nkCmRCBnYERxZanmcpzQSXs1X/AljlKkbJ8qpVIW4clayyef9gWhFbNHWAA==\n"
                    "-----END PUBLIC KEY-----",
                    "is_current": True,
                }
            ]
        }
        response = pretend.stub(
            json=lambda: meta_payload, raise_for_status=lambda: None
        )
        session = pretend.stub(get=pretend.call_recorder(lambda *a, **k: response))
        metrics = pretend.stub(increment=pretend.call_recorder(lambda str: None))
        request = pretend.stub(
            find_service=lambda iface, context: metrics, http=session
        )
        svc = services.GitHubTokenScanningPayloadVerifyService.create_service(
            context=None, request=request
        )
        assert svc._retrieve_public_key_payload() == meta_payload
        assert session.get.calls == [
            pretend.call(
                "https://api.github.com/meta/public_keys/token_scanning", headers={}
            )
        ]

    def test_retrieve_public_key_payload_http_error(self):
        response = pretend.stub(
            status_code=418,
            text="I'm a teapot",
            raise_for_status=pretend.raiser(requests.HTTPError),
        )
        session = pretend.stub(get=lambda *a, **k: response,)
        request = pretend.stub(
            find_service=lambda iface, context: pretend.stub(), http=session
        )
        svc = services.GitHubTokenScanningPayloadVerifyService.create_service(
            context=pretend.stub(), request=request
        )
        with pytest.raises(services.GitHubPublicKeyMetaAPIError) as exc:
            svc._retrieve_public_key_payload()

        assert str(exc.value) == "Invalid response code 418: I'm a teapot"
        assert exc.value.reason == "public_key_api.status.418"

    def test_retrieve_public_key_payload_json_error(self):
        response = pretend.stub(
            text="Still a non-json teapot",
            json=pretend.raiser(json.JSONDecodeError("", "", 3)),
            raise_for_status=lambda: None,
        )
        session = pretend.stub(get=lambda *a, **k: response,)
        request = pretend.stub(
            find_service=lambda iface, context: pretend.stub(), http=session
        )
        svc = services.GitHubTokenScanningPayloadVerifyService.create_service(
            context=pretend.stub(), request=request
        )
        with pytest.raises(services.GitHubPublicKeyMetaAPIError) as exc:
            svc._retrieve_public_key_payload()

        assert str(exc.value) == "Non-JSON response received: Still a non-json teapot"
        assert exc.value.reason == "public_key_api.invalid_json"

    def test_retrieve_public_key_payload_connection_error(self):
        session = pretend.stub(get=pretend.raiser(requests.ConnectionError))
        request = pretend.stub(
            find_service=lambda iface, context: pretend.stub(), http=session
        )
        svc = services.GitHubTokenScanningPayloadVerifyService.create_service(
            context=pretend.stub(), request=request
        )
        with pytest.raises(services.GitHubPublicKeyMetaAPIError) as exc:
            svc._retrieve_public_key_payload()

        assert str(exc.value) == "Could not connect to GitHub"
        assert exc.value.reason == "public_key_api.network_error"

    def test_extract_public_keys(self):
        request = pretend.stub(
            find_service=lambda iface, context: pretend.stub(), http=pretend.stub()
        )
        meta_payload = {
            "public_keys": [
                {
                    "key_identifier": "90a421169f0a406205f1563a953312f0be898d3c"
                    "7b6c06b681aa86a874555f4a",
                    "key": "-----BEGIN PUBLIC KEY-----\n"
                    "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE9MJJHnMfn2+H4xL4YaPDA4RpJqU"
                    "q\nkCmRCBnYERxZanmcpzQSXs1X/AljlKkbJ8qpVIW4clayyef9gWhFbNHWAA==\n"
                    "-----END PUBLIC KEY-----",
                    "is_current": True,
                }
            ]
        }
        svc = services.GitHubTokenScanningPayloadVerifyService.create_service(
            context=pretend.stub(), request=request
        )

        keys = list(svc._extract_public_keys(pubkey_api_data=meta_payload))

        assert keys == [
            {
                "key": "-----BEGIN PUBLIC KEY-----\nMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcD"
                "QgAE9MJJHnMfn2+H4xL4YaPDA4RpJqUq\nkCmRCBnYERxZanmcpzQSXs1X/AljlKkbJ"
                "8qpVIW4clayyef9gWhFbNHWAA==\n-----END PUBLIC KEY-----",
                "key_id": "90a421169f0a406205f1563a953312f0be"
                "898d3c7b6c06b681aa86a874555f4a",
            }
        ]

    @pytest.mark.parametrize(
        "payload, expected",
        [
            ([], "Payload is not a dict but: []"),
            ({}, "Payload misses 'public_keys' attribute"),
            ({"public_keys": None}, "Payload 'public_keys' attribute is not a list"),
            ({"public_keys": [None]}, "Key is not a dict but: None"),
            (
                {"public_keys": [{}]},
                "Missing attribute in key: ['key', 'key_identifier']",
            ),
            (
                {"public_keys": [{"key": "a"}]},
                "Missing attribute in key: ['key_identifier']",
            ),
            (
                {"public_keys": [{"key_identifier": "a"}]},
                "Missing attribute in key: ['key']",
            ),
        ],
    )
    def test_extract_public_keys_error(self, payload, expected):
        request = pretend.stub(
            find_service=lambda iface, context: pretend.stub(), http=pretend.stub()
        )
        svc = services.GitHubTokenScanningPayloadVerifyService.create_service(
            context=pretend.stub(), request=request
        )

        with pytest.raises(services.GitHubPublicKeyMetaAPIError) as exc:
            list(svc._extract_public_keys(pubkey_api_data=payload))

        assert exc.value.reason == "public_key_api.format_error"
        assert str(exc.value) == expected

    def test_check_public_key(self):
        request = pretend.stub(
            find_service=lambda iface, context: pretend.stub(), http=pretend.stub()
        )
        svc = services.GitHubTokenScanningPayloadVerifyService.create_service(
            context=pretend.stub(), request=request
        )

        keys = [
            {"key_id": "a", "key": "b"},
            {"key_id": "c", "key": "d"},
        ]
        assert svc._check_public_key(github_public_keys=keys, key_id="c") == "d"

    def test_check_public_key_error(self):
        request = pretend.stub(
            find_service=lambda iface, context: pretend.stub(), http=pretend.stub()
        )
        svc = services.GitHubTokenScanningPayloadVerifyService.create_service(
            context=pretend.stub(), request=request
        )

        with pytest.raises(services.InvalidTokenLeakRequest) as exc:
            svc._check_public_key(github_public_keys=[], key_id="c")

        assert str(exc.value) == "Key c not found in github public keys"
        assert exc.value.reason == "wrong_key_id"

    def test_check_signature(self):
        request = pretend.stub(
            find_service=lambda iface, context: pretend.stub(), http=pretend.stub()
        )
        svc = services.GitHubTokenScanningPayloadVerifyService.create_service(
            context=pretend.stub(), request=request
        )
        public_key = (
            "-----BEGIN PUBLIC KEY-----\n"
            "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE9MJJHnMfn2+H4xL4YaPDA4RpJqU"
            "q\nkCmRCBnYERxZanmcpzQSXs1X/AljlKkbJ8qpVIW4clayyef9gWhFbNHWAA==\n"
            "-----END PUBLIC KEY-----"
        )
        signature = (
            "MEQCIAfgjgz6Ou/3DXMYZBervz1TKCHFsvwMcbuJhNZse622AiAG86/"
            "cku2XdcmFWNHl2WSJi2fkE8t+auvB24eURaOd2A=="
        )

        payload = (
            '[{"type":"github_oauth_token","token":"cb4985f91f740272c0234202299'
            'f43808034d7f5","url":" https://github.com/github/faketestrepo/blob/'
            'b0dd59c0b500650cacd4551ca5989a6194001b10/production.env"}]'
        )
        assert (
            svc._check_signature(
                payload=payload, public_key=public_key, signature=signature
            )
            is None
        )

    def test_check_signature_invalid_signature(self):
        request = pretend.stub(
            find_service=lambda iface, context: pretend.stub(), http=pretend.stub()
        )
        svc = services.GitHubTokenScanningPayloadVerifyService.create_service(
            context=pretend.stub(), request=request
        )
        public_key = (
            "-----BEGIN PUBLIC KEY-----\n"
            "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE9MJJHnMfn2+H4xL4YaPDA4RpJqU"
            "q\nkCmRCBnYERxZanmcpzQSXs1X/AljlKkbJ8qpVIW4clayyef9gWhFbNHWAA==\n"
            "-----END PUBLIC KEY-----"
        )
        # Changed the initial N for an M
        signature = (
            "NEQCIAfgjgz6Ou/3DXMYZBervz1TKCHFsvwMcbuJhNZse622AiAG86/"
            "cku2XdcmFWNHl2WSJi2fkE8t+auvB24eURaOd2A=="
        )

        payload = (
            '[{"type":"github_oauth_token","token":"cb4985f91f740272c0234202299'
            'f43808034d7f5","url":" https://github.com/github/faketestrepo/blob/'
            'b0dd59c0b500650cacd4551ca5989a6194001b10/production.env"}]'
        )
        with pytest.raises(services.InvalidTokenLeakRequest) as exc:
            svc._check_signature(
                payload=payload, public_key=public_key, signature=signature
            )

        assert str(exc.value) == "Invalid signature"
        assert exc.value.reason == "invalid_signature"

    def test_check_signature_invalid_crypto(self):
        request = pretend.stub(
            find_service=lambda iface, context: pretend.stub(), http=pretend.stub()
        )
        svc = services.GitHubTokenScanningPayloadVerifyService.create_service(
            context=pretend.stub(), request=request
        )
        public_key = ""
        # Changed the initial N for an M
        signature = ""

        payload = "yeah, nope, that won't pass"

        with pytest.raises(services.InvalidTokenLeakRequest) as exc:
            svc._check_signature(
                payload=payload, public_key=public_key, signature=signature
            )

        assert str(exc.value) == "Invalid cryptographic values"
        assert exc.value.reason == "invalid_crypto"


class TestNullGitHubTokenScanningPayloadVerifyService:
    def test_verify_service(self):
        assert verifyClass(
            IGitHubTokenScanningPayloadVerifyService,
            services.NullGitHubTokenScanningPayloadVerifyService,
        )

    def test_verify(self):
        svc = services.NullGitHubTokenScanningPayloadVerifyService()
        assert svc.verify(payload="a", key_id="b", signature="c") is True
