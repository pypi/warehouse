# SPDX-License-Identifier: Apache-2.0

import datetime
import uuid

from types import SimpleNamespace

import freezegun
import passlib.exc
import pytest
import requests
import responses

from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.structs import AttestationFormat, PublicKeyCredentialType
from webauthn.registration.verify_registration_response import VerifiedRegistration
from zope.interface.verify import verifyClass

from warehouse.accounts import services
from warehouse.accounts.interfaces import (
    BurnedRecoveryCode,
    EmailReputationResult,
    IDomainStatusService,
    IEmailBreachedService,
    IEmailReputationService,
    InvalidRecoveryCode,
    IPasswordBreachedService,
    ITokenService,
    IUserService,
    NoRecoveryCodes,
    TokenExpired,
    TokenInvalid,
    TokenMissing,
    TooManyEmailReputationChecks,
    TooManyEmailsAdded,
    TooManyFailedLogins,
)
from warehouse.accounts.models import (
    DisableReason,
    ProhibitedUserName,
    TermsOfServiceEngagement,
    User,
    UserTermsOfServiceEngagement,
)
from warehouse.constants import RateLimitPeriod
from warehouse.events.tags import EventTag
from warehouse.metrics import NullMetrics
from warehouse.rate_limiting import DummyRateLimiter, RateLimiter
from warehouse.rate_limiting.interfaces import IRateLimiter
from warehouse.utils import otp, webauthn

from ...common.constants import REMOTE_ADDR
from ...common.db.accounts import (
    EmailFactory,
    OAuthAccountAssociationFactory,
    UserFactory,
    UserTermsOfServiceEngagementFactory,
    UserUniqueLoginFactory,
)


@pytest.fixture
def http_session(mocker):
    """A real ``requests.Session`` with a spied ``get``, for ``responses`` tests."""
    session = requests.Session()
    mocker.spy(session, "get")
    return session


@pytest.fixture
def make_limiter(mocker):
    """Build an autospec'd ``RateLimiter`` with the given method return values."""

    def _make(**return_values):
        limiter = mocker.create_autospec(RateLimiter, instance=True)
        for method, value in return_values.items():
            getattr(limiter, method).return_value = value
        return limiter

    return _make


class TestDatabaseUserService:
    def test_verify_service(self):
        assert verifyClass(IUserService, services.DatabaseUserService)

    def test_service_creation(self, mocker):
        crypt_context_cls = mocker.patch.object(services, "CryptContext", autospec=True)

        session = mocker.sentinel.session
        service = services.DatabaseUserService(
            session, metrics=NullMetrics(), remote_addr=REMOTE_ADDR
        )

        assert service.db is session
        assert service.hasher is crypt_context_cls.return_value
        crypt_context_cls.assert_called_once_with(
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

    def test_service_creation_ratelimiters(self, mocker):
        crypt_context_cls = mocker.patch.object(services, "CryptContext", autospec=True)

        ratelimiters = {
            "user.login": mocker.sentinel.user_login,
            "global.login": mocker.sentinel.global_login,
        }

        session = mocker.sentinel.session
        service = services.DatabaseUserService(
            session,
            metrics=NullMetrics(),
            remote_addr=REMOTE_ADDR,
            ratelimiters=ratelimiters,
        )

        assert service.db is session
        assert service.ratelimiters == ratelimiters
        assert service.hasher is crypt_context_cls.return_value
        crypt_context_cls.assert_called_once_with(
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

    def test_skips_ip_rate_limiter(self, user_service, metrics, make_limiter, mocker):
        user = UserFactory.create()
        resets = mocker.sentinel.resets
        limiter = make_limiter(test=False, resets_in=resets)
        user_service.ratelimiters["ip.login"] = limiter
        user_service.remote_addr = None

        user_service.check_password(user.id, "password")

        limiter.test.assert_not_called()
        limiter.resets_in.assert_not_called()

    def test_username_is_not_prohibited(self, user_service):
        assert user_service.username_is_prohibited("my_username") is False

    def test_username_is_prohibited(self, user_service):
        user = UserFactory.create()
        user_service.db.add(
            ProhibitedUserName(
                name="my_username",
                comment="blah",
                prohibited_by=user,
            )
        )
        assert user_service.username_is_prohibited("my_username") is True

    def test_find_userid_nonexistent_user(self, user_service):
        assert user_service.find_userid("my_username") is None

    def test_find_userid_existing_user(self, user_service):
        user = UserFactory.create()
        assert user_service.find_userid(user.username) == user.id

    def test_check_password_global_rate_limited(
        self, user_service, metrics, mocker, make_limiter
    ):
        resets = mocker.sentinel.resets
        limiter = make_limiter(test=False, resets_in=resets)
        user_service.ratelimiters["global.login"] = limiter

        with pytest.raises(TooManyFailedLogins) as excinfo:
            user_service.check_password(uuid.uuid4(), None, tags=["foo"])

        assert excinfo.value.resets_in is resets
        assert metrics.increment.call_args_list == [
            mocker.call(
                "warehouse.authentication.start",
                tags=["foo", "mechanism:check_password"],
            ),
            mocker.call(
                "warehouse.authentication.ratelimited",
                tags=["foo", "mechanism:check_password", "ratelimiter:global"],
            ),
        ]

    def test_check_password_nonexistent_user(self, user_service, metrics, mocker):
        assert not user_service.check_password(uuid.uuid4(), None, tags=["foo"])
        assert metrics.increment.call_args_list == [
            mocker.call(
                "warehouse.authentication.start",
                tags=["foo", "mechanism:check_password"],
            ),
            mocker.call(
                "warehouse.authentication.failure",
                tags=["foo", "mechanism:check_password", "failure_reason:user"],
            ),
        ]

    def test_check_password_user_rate_limited(
        self, user_service, metrics, mocker, make_limiter
    ):
        user = UserFactory.create()
        resets = mocker.sentinel.resets
        limiter = make_limiter(test=False, resets_in=resets)
        user_service.ratelimiters["user.login"] = limiter

        with pytest.raises(TooManyFailedLogins) as excinfo:
            user_service.check_password(user.id, None)

        assert excinfo.value.resets_in is resets
        limiter.test.assert_called_once_with(user.id)
        limiter.resets_in.assert_called_once_with(user.id)
        assert metrics.increment.call_args_list == [
            mocker.call(
                "warehouse.authentication.start", tags=["mechanism:check_password"]
            ),
            mocker.call(
                "warehouse.authentication.ratelimited",
                tags=["mechanism:check_password", "ratelimiter:user"],
            ),
        ]

    def test_check_password_ip_rate_limited(
        self, user_service, metrics, mocker, make_limiter
    ):
        user = UserFactory.create()
        resets = mocker.sentinel.resets
        limiter = make_limiter(test=False, resets_in=resets)
        user_service.ratelimiters["ip.login"] = limiter

        with pytest.raises(TooManyFailedLogins) as excinfo:
            user_service.check_password(user.id, None)

        assert excinfo.value.resets_in is resets
        limiter.test.assert_called_once_with(REMOTE_ADDR)
        limiter.resets_in.assert_called_once_with(REMOTE_ADDR)
        assert metrics.increment.call_args_list == [
            mocker.call(
                "warehouse.authentication.start", tags=["mechanism:check_password"]
            ),
            mocker.call(
                "warehouse.authentication.ratelimited",
                tags=["mechanism:check_password", "ratelimiter:ip"],
            ),
        ]

    def test_check_password_invalid(self, user_service, metrics, mocker):
        user = UserFactory.create(clear_pwd="password")
        mocker.spy(user_service.hasher, "verify_and_update")

        assert not user_service.check_password(user.id, "user password")
        user_service.hasher.verify_and_update.assert_called_once_with(
            "user password", user.password
        )
        assert metrics.increment.call_args_list == [
            mocker.call(
                "warehouse.authentication.start", tags=["mechanism:check_password"]
            ),
            mocker.call(
                "warehouse.authentication.failure",
                tags=["mechanism:check_password", "failure_reason:password"],
            ),
        ]

    def test_check_password_catches_bcrypt_exception(
        self, user_service, metrics, mocker
    ):
        user = UserFactory.create()

        mocker.patch.object(
            user_service.hasher,
            "verify_and_update",
            autospec=True,
            side_effect=passlib.exc.PasswordValueError,
        )

        assert not user_service.check_password(user.id, "user password")
        user_service.hasher.verify_and_update.assert_called_once_with(
            "user password", user.password
        )
        assert metrics.increment.call_args_list == [
            mocker.call(
                "warehouse.authentication.start", tags=["mechanism:check_password"]
            ),
            mocker.call(
                "warehouse.authentication.failure",
                tags=["mechanism:check_password", "failure_reason:password"],
            ),
        ]

    def test_check_password_valid(self, user_service, metrics, mocker):
        user = UserFactory.create(clear_pwd="user password")
        mocker.spy(user_service.hasher, "verify_and_update")

        assert user_service.check_password(user.id, "user password", tags=["bar"])
        user_service.hasher.verify_and_update.assert_called_once_with(
            "user password", user.password
        )
        assert metrics.increment.call_args_list == [
            mocker.call(
                "warehouse.authentication.start",
                tags=["bar", "mechanism:check_password"],
            ),
            mocker.call(
                "warehouse.authentication.ok", tags=["bar", "mechanism:check_password"]
            ),
        ]

    @pytest.mark.parametrize(
        "password",
        [
            (
                "$argon2id$v=19$m=8,t=1,p=1$"
                "w/gfo5QSQihFyHlvDcE4pw$Hd4KENg+xDlq2bfeGUEYSieIXXL/c1NfTr0ZkYueO2Y"
            ),
            (
                "$bcrypt-sha256$v=2,t=2b,r=12$"
                "DqC0lms6x9Dh6XesvIJvVe$hBbYe9JfdjyorOFcS3rv5BhmuSIyXD6"
            ),
            "$2b$12$2t/EVU3H9b3c5iR6GdELZOwCoyrT518DgCpNxHbX.S1IxV6eEEDhC",
            "bcrypt$$2b$12$EhhZDxGr/7HIKYRGMngC.O4sQx68vkaISSnSGZ6s8iOfaGy6l9cma",
        ],
    )
    def test_check_password_updates(self, user_service, password):
        """
        This test confirms passlib is actually working,
        see https://github.com/pypi/warehouse/issues/15454
        """
        user = UserFactory.create(password=password)

        assert user_service.check_password(user.id, "password")
        assert user.password.startswith("$argon2id$v=19$m=1024,t=6,p=6$")
        assert user_service.check_password(user.id, "password")

    def test_hash_is_upgraded(self, user_service, mocker):
        user = UserFactory.create()
        password = user.password
        mocker.patch.object(
            user_service.hasher,
            "verify_and_update",
            autospec=True,
            return_value=(True, "new password"),
        )

        assert user_service.check_password(user.id, "user password")
        user_service.hasher.verify_and_update.assert_called_once_with(
            "user password", password
        )
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
        new_email = user_service.add_email(user.id, email, primary=False)

        assert new_email.email == email
        assert new_email.user == user
        assert not new_email.primary
        assert not new_email.verified

    def test_add_email_defaults_to_primary(self, user_service):
        user = UserFactory.create()
        email1 = "foo@example.com"
        email2 = "bar@example.com"
        new_email1 = user_service.add_email(user.id, email1)
        new_email2 = user_service.add_email(user.id, email2)

        assert new_email1.email == email1
        assert new_email1.user == user
        assert new_email1.primary
        assert not new_email1.verified

        assert new_email2.email == email2
        assert new_email2.user == user
        assert not new_email2.primary
        assert not new_email2.verified

    def test_add_email_rate_limited(self, user_service, metrics, make_limiter, mocker):
        resets = mocker.sentinel.resets
        limiter = make_limiter(test=False, resets_in=resets)
        user_service.ratelimiters["email.add"] = limiter

        user = UserFactory.build()

        with pytest.raises(TooManyEmailsAdded) as excinfo:
            user_service.add_email(user.id, user.email)

        assert excinfo.value.resets_in is resets
        limiter.test.assert_called_once_with(REMOTE_ADDR)
        limiter.resets_in.assert_called_once_with(REMOTE_ADDR)
        metrics.increment.assert_called_once_with(
            "warehouse.email.add.ratelimited", tags=["ratelimiter:email.add"]
        )

    def test_add_email_bypass_ratelimit(
        self, user_service, metrics, make_limiter, mocker
    ):
        resets = mocker.sentinel.resets
        limiter = make_limiter(test=False, resets_in=resets)
        user_service.ratelimiters["email.add"] = limiter

        user = UserFactory.create()
        new_email = user_service.add_email(user.id, "foo@example.com", ratelimit=False)

        assert new_email.email == "foo@example.com"
        assert not new_email.verified
        limiter.test.assert_not_called()
        limiter.resets_in.assert_not_called()
        metrics.increment.assert_not_called()

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

    def test_get_users_by_prefix(self, user_service):
        user = UserFactory.create()
        found_users = user_service.get_users_by_prefix(user.username[:3])

        assert len(found_users) == 1
        assert user.id == found_users[0].id

    def test_get_user_by_email_failure(self, user_service):
        found_user = user_service.get_user_by_email("example@email.com")
        user_service.db.flush()

        assert found_user is None

    def test_get_admin_user(self, user_service):
        admin = UserFactory.create(is_superuser=True, username="admin")

        assert user_service.get_admin_user() == admin

    def test_set_project_create_ratelimit(self, user_service, db_request):
        user = UserFactory.create()
        db_request.user = UserFactory.create()

        limit = user_service.set_project_create_ratelimit(
            user.id, db_request, 25, RateLimitPeriod.Day
        )

        assert limit == "25 per day"
        assert user.project_create_ratelimit_count == 25
        assert user.project_create_ratelimit_period is RateLimitPeriod.Day
        event = user.events.one()
        assert event.tag == "account:project_create_ratelimit:change"
        assert event.additional == {
            "old_project_create_ratelimit_string": None,
            "new_project_create_ratelimit_string": "25 per day",
            "actor": db_request.user.username,
        }

    def test_set_project_create_ratelimit_clears_override(
        self, user_service, db_request
    ):
        """A None count clears the override and records what it replaced."""
        user = UserFactory.create(
            project_create_ratelimit_count=25,
            project_create_ratelimit_period=RateLimitPeriod.Day,
        )
        db_request.user = UserFactory.create()

        limit = user_service.set_project_create_ratelimit(
            user.id, db_request, None, RateLimitPeriod.Hour
        )

        assert limit is None
        assert user.project_create_ratelimit_string is None
        event = user.events.one()
        assert event.additional["old_project_create_ratelimit_string"] == "25 per day"
        assert event.additional["new_project_create_ratelimit_string"] is None

    @pytest.mark.parametrize(
        ("reason", "expected"),
        [
            (None, None),
            (
                DisableReason.CompromisedPassword,
                DisableReason.CompromisedPassword.value,
            ),
        ],
    )
    def test_disable_password(self, user_service, db_request, reason, expected, mocker):
        request = db_request
        user = UserFactory.create()
        mocker.patch.object(user, "record_event", autospec=True, return_value=None)

        # Need to give the user a good password first.
        user_service.update_user(user.id, password="foo")
        assert user.password != "!"

        # Now we'll actually test our disable function.
        user_service.disable_password(user.id, reason=reason, request=request)
        assert user.password == "!"

        user.record_event.assert_called_once_with(
            tag=EventTag.Account.PasswordDisabled,
            request=request,
            additional={"reason": expected},
        )

    @pytest.mark.parametrize(
        ("disabled", "reason"),
        [(True, None), (True, DisableReason.CompromisedPassword), (False, None)],
    )
    def test_is_disabled(self, user_service, db_request, disabled, reason):
        request = db_request
        user = UserFactory.create()
        user_service.update_user(user.id, password="foo")
        if disabled:
            user_service.disable_password(user.id, reason=reason, request=request)
        assert user_service.is_disabled(user.id) == (disabled, reason)

    def test_is_disabled_user_frozen(self, user_service):
        user = UserFactory.create(is_frozen=True)
        assert user_service.is_disabled(user.id) == (True, DisableReason.AccountFrozen)

    def test_updating_password_undisables(self, user_service, db_request):
        request = db_request
        user = UserFactory.create()
        user_service.disable_password(
            user.id, reason=DisableReason.CompromisedPassword, request=request
        )
        assert user_service.is_disabled(user.id) == (
            True,
            DisableReason.CompromisedPassword,
        )
        user_service.update_user(user.id, password="foo")
        assert user_service.is_disabled(user.id) == (False, None)

    def test_has_two_factor(self, user_service):
        user = UserFactory.create(totp_secret=None)
        assert not user_service.has_two_factor(user.id)

        user_service.update_user(user.id, totp_secret=b"foobar")
        assert user_service.has_two_factor(user.id)

    def test_has_totp(self, user_service):
        user = UserFactory.create(totp_secret=None)
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
        [(None, True), ("000000", True), ("000000", False)],
    )
    def test_check_totp_value(self, user_service, last_totp_value, valid, mocker):
        mocker.patch.object(otp, "verify_totp", autospec=True, return_value=valid)

        user = UserFactory.create()
        user_service.update_user(
            user.id, last_totp_value=last_totp_value, totp_secret=b"foobar"
        )
        user_service.add_email(user.id, "foo@bar.com", primary=True, verified=True)

        assert user_service.check_totp_value(user.id, b"123456") == valid

    def test_check_totp_value_reused(self, user_service):
        user = UserFactory.create()
        user_service.update_user(
            user.id, last_totp_value="123456", totp_secret=b"foobar"
        )

        assert not user_service.check_totp_value(user.id, b"123456")

    def test_check_totp_out_of_sync(self, mocker, metrics, user_service):
        user = UserFactory.create()
        mocker.patch.object(otp, "verify_totp", side_effect=otp.OutOfSyncTOTPError)

        with pytest.raises(otp.OutOfSyncTOTPError):
            user_service.check_totp_value(user.id, b"123456")

        assert metrics.increment.call_args_list == [
            mocker.call(
                "warehouse.authentication.two_factor.start",
                tags=["mechanism:check_totp_value"],
            ),
            mocker.call(
                "warehouse.authentication.two_factor.failure",
                tags=["mechanism:check_totp_value", "failure_reason:out_of_sync"],
            ),
        ]

    def test_check_totp_value_no_secret(self, user_service):
        user = UserFactory.create()
        with pytest.raises(otp.InvalidTOTPError):
            user_service.check_totp_value(user.id, b"123456")

    def test_check_totp_ip_rate_limited(
        self, user_service, metrics, mocker, make_limiter
    ):
        resets = mocker.sentinel.resets
        limiter = make_limiter(test=False, resets_in=resets)
        user_service.ratelimiters["2fa.ip"] = limiter

        with pytest.raises(TooManyFailedLogins) as excinfo:
            user_service.check_totp_value(uuid.uuid4(), b"123456", tags=["foo"])

        assert excinfo.value.resets_in is resets
        assert metrics.increment.call_args_list == [
            mocker.call(
                "warehouse.authentication.two_factor.start",
                tags=["foo", "mechanism:check_totp_value"],
            ),
            mocker.call(
                "warehouse.authentication.ratelimited",
                tags=["foo", "mechanism:check_totp_value", "ratelimiter:ip"],
            ),
        ]

    def test_check_totp_value_user_rate_limited(
        self, user_service, metrics, mocker, make_limiter
    ):
        user = UserFactory.create()
        resets = mocker.sentinel.resets
        limiter = make_limiter(test=False, resets_in=resets)
        user_service.ratelimiters["2fa.user"] = limiter

        with pytest.raises(TooManyFailedLogins) as excinfo:
            user_service.check_totp_value(user.id, b"123456")

        assert excinfo.value.resets_in is resets
        limiter.test.assert_called_once_with(user.id)
        limiter.resets_in.assert_called_once_with(user.id)
        assert metrics.increment.call_args_list == [
            mocker.call(
                "warehouse.authentication.two_factor.start",
                tags=["mechanism:check_totp_value"],
            ),
            mocker.call(
                "warehouse.authentication.ratelimited",
                tags=["mechanism:check_totp_value", "ratelimiter:user"],
            ),
        ]

    def test_check_totp_value_invalid_secret(self, user_service, mocker, make_limiter):
        user = UserFactory.create(totp_secret=None)
        limiter = make_limiter(test=True)
        user_service.ratelimiters["2fa.user"] = limiter
        user_service.ratelimiters["2fa.ip"] = limiter

        valid = user_service.check_totp_value(user.id, b"123456")

        assert not valid
        assert limiter.hit.call_args_list == [
            mocker.call(user.id),
            mocker.call(REMOTE_ADDR),
        ]

    def test_check_totp_value_invalid_totp(
        self, user_service, monkeypatch, mocker, make_limiter
    ):
        user = UserFactory.create()
        limiter = make_limiter(test=True)
        user_service.get_totp_secret = lambda uid: "secret"
        monkeypatch.setattr(otp, "verify_totp", lambda secret, value: False)
        user_service.ratelimiters["2fa.user"] = limiter
        user_service.ratelimiters["2fa.ip"] = limiter

        valid = user_service.check_totp_value(user.id, b"123456")

        assert not valid
        assert limiter.test.call_args_list == [
            mocker.call(REMOTE_ADDR),
            mocker.call(user.id),
        ]
        assert limiter.hit.call_args_list == [
            mocker.call(user.id),
            mocker.call(REMOTE_ADDR),
        ]

    def test_check_totp_value_with_2fa_rate_limiters(
        self, db_session, metrics, monkeypatch, make_limiter
    ):
        """Test that check_totp_value uses new 2FA rate limiters when available."""
        user = UserFactory.create()

        # Create mocked rate limiters
        ratelimiters = {
            "user.login": make_limiter(test=True),
            "ip.login": make_limiter(test=True),
            "global.login": make_limiter(test=True),
            "2fa.user": make_limiter(test=True),
            "2fa.ip": make_limiter(test=True),
        }

        user_service = services.DatabaseUserService(
            db_session,
            metrics=metrics,
            remote_addr=REMOTE_ADDR,
            ratelimiters=ratelimiters,
        )

        # Mock TOTP verification to fail
        monkeypatch.setattr(otp, "verify_totp", lambda secret, value: False)
        user_service.update_user(user.id, totp_secret=b"secret")

        result = user_service.check_totp_value(user.id, b"123456")

        assert not result
        # Should use 2FA rate limiters, not login rate limiters
        ratelimiters["2fa.user"].test.assert_called_once_with(user.id)
        ratelimiters["2fa.ip"].test.assert_called_once_with(REMOTE_ADDR)

    def test_check_2fa_ratelimits_ip_limited(
        self, db_session, metrics, make_limiter, mocker
    ):
        """Test IP-based 2FA rate limiting."""
        user = UserFactory.create()
        resets = mocker.sentinel.resets

        ratelimiters = {
            "2fa.ip": make_limiter(test=False, resets_in=resets),
            "2fa.user": make_limiter(test=True),
        }

        user_service = services.DatabaseUserService(
            db_session,
            metrics=metrics,
            remote_addr=REMOTE_ADDR,
            ratelimiters=ratelimiters,
        )

        with pytest.raises(TooManyFailedLogins) as excinfo:
            user_service._check_2fa_ratelimits(userid=user.id, tags=["test_tag"])

        assert excinfo.value.resets_in is resets
        ratelimiters["2fa.ip"].test.assert_called_once_with(REMOTE_ADDR)
        metrics.increment.assert_called_once_with(
            "warehouse.authentication.ratelimited", tags=["test_tag", "ratelimiter:ip"]
        )

    def test_check_2fa_ratelimits_user_limited(
        self, db_session, metrics, make_limiter, mocker
    ):
        """Test user-based 2FA rate limiting."""
        user = UserFactory.create()
        resets = mocker.sentinel.resets

        ratelimiters = {
            "2fa.ip": make_limiter(test=True),
            "2fa.user": make_limiter(test=False, resets_in=resets),
        }

        user_service = services.DatabaseUserService(
            db_session,
            metrics=metrics,
            remote_addr=REMOTE_ADDR,
            ratelimiters=ratelimiters,
        )

        with pytest.raises(TooManyFailedLogins) as excinfo:
            user_service._check_2fa_ratelimits(userid=user.id, tags=["test_tag"])

        assert excinfo.value.resets_in is resets
        ratelimiters["2fa.user"].test.assert_called_once_with(user.id)
        metrics.increment.assert_called_once_with(
            "warehouse.authentication.ratelimited",
            tags=["test_tag", "ratelimiter:user"],
        )

    def test_check_2fa_ratelimits_no_remote_addr(
        self, db_session, metrics, make_limiter
    ):
        """Test 2FA rate limiting when remote_addr is None."""
        user = UserFactory.create()

        ratelimiters = {
            "2fa.ip": make_limiter(test=True),
            "2fa.user": make_limiter(test=True),
        }

        user_service = services.DatabaseUserService(
            db_session,
            metrics=metrics,
            remote_addr=None,
            ratelimiters=ratelimiters,
        )

        # Should not raise, IP check should be skipped
        user_service._check_2fa_ratelimits(userid=user.id)

        # IP limiter should not be called
        ratelimiters["2fa.ip"].test.assert_not_called()

    def test_hit_2fa_ratelimits(self, db_session, metrics, make_limiter):
        """Test hitting 2FA rate limits records properly."""
        user = UserFactory.create()

        ratelimiters = {
            "2fa.user": make_limiter(),
            "2fa.ip": make_limiter(),
        }

        user_service = services.DatabaseUserService(
            db_session,
            metrics=metrics,
            remote_addr=REMOTE_ADDR,
            ratelimiters=ratelimiters,
        )

        user_service._hit_2fa_ratelimits(userid=user.id)

        ratelimiters["2fa.user"].hit.assert_called_once_with(user.id)
        ratelimiters["2fa.ip"].hit.assert_called_once_with(REMOTE_ADDR)

    def test_hit_2fa_ratelimits_no_remote_addr(self, db_session, metrics, make_limiter):
        """Test hitting 2FA rate limits when remote_addr is None."""
        user = UserFactory.create()

        ratelimiters = {
            "2fa.user": make_limiter(),
            "2fa.ip": make_limiter(),
        }

        user_service = services.DatabaseUserService(
            db_session,
            metrics=metrics,
            remote_addr=None,
            ratelimiters=ratelimiters,
        )

        user_service._hit_2fa_ratelimits(userid=user.id)

        # Only user limiter should be hit
        ratelimiters["2fa.user"].hit.assert_called_once_with(user.id)
        ratelimiters["2fa.ip"].hit.assert_not_called()

    def test_verify_webauthn_assertion_rate_limited(
        self, db_session, metrics, make_limiter, mocker
    ):
        """Test that verify_webauthn_assertion uses 2FA rate limiters."""
        user = UserFactory.create()
        resets = mocker.sentinel.resets

        ratelimiters = {
            "2fa.user": make_limiter(test=False, resets_in=resets),
            "2fa.ip": make_limiter(test=True),
        }

        user_service = services.DatabaseUserService(
            db_session,
            metrics=metrics,
            remote_addr=REMOTE_ADDR,
            ratelimiters=ratelimiters,
        )

        with pytest.raises(TooManyFailedLogins) as excinfo:
            user_service.verify_webauthn_assertion(
                user.id,
                b"assertion",
                challenge=b"challenge",
                origin="https://example.com",
                rp_id="example.com",
            )

        assert excinfo.value.resets_in is resets
        ratelimiters["2fa.user"].test.assert_called_once_with(user.id)
        metrics.increment.assert_called_once_with(
            "warehouse.authentication.ratelimited",
            tags=["mechanism:webauthn", "ratelimiter:user"],
        )

    def test_verify_webauthn_assertion_failure_hits_ratelimits(
        self, db_session, metrics, make_limiter, mocker
    ):
        """Test that failed WebAuthn assertions hit 2FA rate limiters."""
        user = UserFactory.create()

        ratelimiters = {
            "2fa.user": make_limiter(test=True),
            "2fa.ip": make_limiter(test=True),
        }

        user_service = services.DatabaseUserService(
            db_session,
            metrics=metrics,
            remote_addr=REMOTE_ADDR,
            ratelimiters=ratelimiters,
        )

        # Mock webauthn to raise AuthenticationRejectedError
        mocker.patch.object(
            webauthn,
            "verify_assertion_response",
            autospec=True,
            side_effect=webauthn.AuthenticationRejectedError("test error"),
        )

        with pytest.raises(webauthn.AuthenticationRejectedError):
            user_service.verify_webauthn_assertion(
                user.id,
                b"assertion",
                challenge=b"challenge",
                origin="https://example.com",
                rp_id="example.com",
            )

        ratelimiters["2fa.user"].hit.assert_called_once_with(user.id)
        ratelimiters["2fa.ip"].hit.assert_called_once_with(REMOTE_ADDR)

    def test_check_recovery_code_uses_2fa_ratelimits(
        self, db_session, metrics, mocker, make_limiter
    ):
        """Test that check_recovery_code uses 2FA rate limiters."""
        user = UserFactory.create()
        resets = mocker.sentinel.resets

        ratelimiters = {
            "2fa.ip": make_limiter(test=False, resets_in=resets),
            "2fa.user": make_limiter(test=True),
        }

        user_service = services.DatabaseUserService(
            db_session,
            metrics=metrics,
            remote_addr=REMOTE_ADDR,
            ratelimiters=ratelimiters,
        )

        with pytest.raises(TooManyFailedLogins) as excinfo:
            user_service.check_recovery_code(user.id, "code")

        assert excinfo.value.resets_in is resets
        ratelimiters["2fa.ip"].test.assert_called_once_with(REMOTE_ADDR)
        assert metrics.increment.call_args_list == [
            mocker.call("warehouse.authentication.recovery_code.start"),
            mocker.call(
                "warehouse.authentication.ratelimited",
                tags=["mechanism:check_recovery_code", "ratelimiter:ip"],
            ),
        ]

    def test_get_webauthn_credential_options(self, user_service):
        user = UserFactory.create()
        options = user_service.get_webauthn_credential_options(
            user.id,
            challenge=b"fake_challenge",
            rp_name="fake_rp_name",
            rp_id="fake_rp_id",
        )

        assert options["user"]["id"] == bytes_to_base64url(str(user.id).encode())
        assert options["user"]["name"] == user.username
        assert options["user"]["displayName"] == user.name
        assert options["challenge"] == bytes_to_base64url(b"fake_challenge")
        assert options["rp"]["name"] == "fake_rp_name"
        assert options["rp"]["id"] == "fake_rp_id"
        assert "icon" not in options["user"]

    def test_get_webauthn_credential_options_for_blank_name(self, user_service):
        user = UserFactory.create(name="")

        options = user_service.get_webauthn_credential_options(
            user.id,
            challenge=b"fake_challenge",
            rp_name="fake_rp_name",
            rp_id="fake_rp_id",
        )

        assert options["user"]["name"] == user.username
        assert options["user"]["displayName"] == user.username

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
            user.id, challenge=b"fake_challenge", rp_id="fake_rp_id"
        )

        assert options["challenge"] == bytes_to_base64url(b"fake_challenge")
        assert options["rpId"] == "fake_rp_id"
        assert options["allowCredentials"][0]["id"] == user.webauthn[0].credential_id

    def test_verify_webauthn_credential(self, user_service, mocker):
        user = UserFactory.create()
        user_service.add_webauthn(
            user.id,
            label="test_label",
            credential_id="foo",
            public_key="bar",
            sign_count=1,
        )

        fake_validated_credential = VerifiedRegistration(
            credential_id=b"bar",
            credential_public_key=b"bar",
            sign_count=0,
            aaguid="wutang",
            fmt=AttestationFormat.NONE,
            credential_type=PublicKeyCredentialType.PUBLIC_KEY,
            user_verified=False,
            attestation_object=b"foobar",
            credential_device_type="single_device",
            credential_backed_up=False,
        )
        verify_registration_response = mocker.patch.object(
            webauthn,
            "verify_registration_response",
            autospec=True,
            return_value=fake_validated_credential,
        )

        validated_credential = user_service.verify_webauthn_credential(
            mocker.sentinel.credential,
            challenge=mocker.sentinel.challenge,
            rp_id=mocker.sentinel.rp_id,
            origin=mocker.sentinel.origin,
        )

        assert validated_credential is fake_validated_credential
        verify_registration_response.assert_called_once_with(
            mocker.sentinel.credential,
            challenge=mocker.sentinel.challenge,
            rp_id=mocker.sentinel.rp_id,
            origin=mocker.sentinel.origin,
        )

    def test_verify_webauthn_credential_already_in_use(self, user_service, mocker):
        user = UserFactory.create()
        user_service.add_webauthn(
            user.id,
            label="test_label",
            credential_id=bytes_to_base64url(b"foo"),
            public_key=b"bar",
            sign_count=1,
        )

        fake_validated_credential = VerifiedRegistration(
            credential_id=b"foo",
            credential_public_key=b"bar",
            sign_count=0,
            aaguid="wutang",
            fmt=AttestationFormat.NONE,
            credential_type=PublicKeyCredentialType.PUBLIC_KEY,
            user_verified=False,
            attestation_object=b"foobar",
            credential_device_type="single_device",
            credential_backed_up=False,
        )
        mocker.patch.object(
            webauthn,
            "verify_registration_response",
            autospec=True,
            return_value=fake_validated_credential,
        )

        with pytest.raises(webauthn.RegistrationRejectedError):
            user_service.verify_webauthn_credential(
                mocker.sentinel.credential,
                challenge=mocker.sentinel.challenge,
                rp_id=mocker.sentinel.rp_id,
                origin=mocker.sentinel.origin,
            )

    def test_verify_webauthn_assertion(self, user_service, mocker):
        user = UserFactory.create()
        user_service.add_webauthn(
            user.id,
            label="test_label",
            credential_id="foo",
            public_key="bar",
            sign_count=1,
        )

        mocker.patch.object(
            webauthn, "verify_assertion_response", autospec=True, return_value=2
        )

        updated_sign_count = user_service.verify_webauthn_assertion(
            user.id,
            mocker.sentinel.assertion,
            challenge=mocker.sentinel.challenge,
            origin=mocker.sentinel.origin,
            rp_id=mocker.sentinel.rp_id,
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

        with pytest.raises(NoRecoveryCodes):
            user_service.get_recovery_codes(user.id)

        user_service.generate_recovery_codes(user.id)

        assert len(user_service.get_recovery_codes(user.id)) == 8

    def test_get_recovery_code(self, user_service):
        user = UserFactory.create()

        with pytest.raises(NoRecoveryCodes):
            user_service.get_recovery_code(user.id, "invalid")

        codes = user_service.generate_recovery_codes(user.id)

        with pytest.raises(InvalidRecoveryCode):
            user_service.get_recovery_code(user.id, "invalid")

        code = user_service.get_recovery_code(user.id, codes[0])

        assert user_service.hasher.verify(codes[0], code.code)

    def test_get_recovery_code_oversized_input(self, user_service):
        user = UserFactory.create()
        codes = user_service.generate_recovery_codes(user.id)
        assert len(codes) == 8

        # An oversized input should raise InvalidRecoveryCode,
        # not passlib's PasswordSizeError.
        with pytest.raises(InvalidRecoveryCode):
            user_service.get_recovery_code(user.id, "a" * 5000)

    def test_generate_recovery_codes(self, user_service):
        user = UserFactory.create()

        assert not user_service.has_recovery_codes(user.id)

        with pytest.raises(NoRecoveryCodes):
            user_service.get_recovery_codes(user.id)

        codes = user_service.generate_recovery_codes(user.id)

        assert len(codes) == 8
        assert len(user_service.get_recovery_codes(user.id)) == 8

    def test_check_recovery_code(self, user_service, metrics, mocker):
        user = UserFactory.create()

        with pytest.raises(NoRecoveryCodes):
            user_service.check_recovery_code(user.id, "no codes yet")

        codes = user_service.generate_recovery_codes(user.id)

        assert len(codes) == 8
        assert len(user_service.get_recovery_codes(user.id)) == 8
        assert not user_service.get_recovery_code(user.id, codes[0]).burned

        assert user_service.check_recovery_code(user.id, codes[0])

        # Once used, the code should not be accepted again.
        assert len(user_service.get_recovery_codes(user.id)) == 8

        with pytest.raises(BurnedRecoveryCode):
            user_service.check_recovery_code(user.id, codes[0])

        assert user_service.get_recovery_code(user.id, codes[0]).burned

        assert metrics.increment.call_args_list == [
            mocker.call("warehouse.authentication.recovery_code.start"),
            mocker.call(
                "warehouse.authentication.recovery_code.failure",
                tags=["failure_reason:no_recovery_codes"],
            ),
            mocker.call("warehouse.authentication.recovery_code.start"),
            mocker.call("warehouse.authentication.recovery_code.ok"),
            mocker.call("warehouse.authentication.recovery_code.start"),
            mocker.call(
                "warehouse.authentication.recovery_code.failure",
                tags=["failure_reason:burned_recovery_code"],
            ),
        ]

    def test_check_recovery_code_ip_rate_limited(
        self, user_service, metrics, mocker, make_limiter
    ):
        resets = mocker.sentinel.resets
        limiter = make_limiter(test=False, resets_in=resets)
        user_service.ratelimiters["2fa.ip"] = limiter

        with pytest.raises(TooManyFailedLogins) as excinfo:
            user_service.check_recovery_code(uuid.uuid4(), "recovery_code")

        assert excinfo.value.resets_in is resets
        assert metrics.increment.call_args_list == [
            mocker.call("warehouse.authentication.recovery_code.start"),
            mocker.call(
                "warehouse.authentication.ratelimited",
                tags=["mechanism:check_recovery_code", "ratelimiter:ip"],
            ),
        ]

    def test_check_recovery_code_user_rate_limited(
        self, user_service, metrics, mocker, make_limiter
    ):
        user = UserFactory.create()
        resets = mocker.sentinel.resets
        limiter = make_limiter(test=False, resets_in=resets)
        user_service.ratelimiters["2fa.ip"] = limiter

        with pytest.raises(TooManyFailedLogins) as excinfo:
            user_service.check_recovery_code(user.id, "recovery_code")

        assert excinfo.value.resets_in is resets
        limiter.test.assert_called_once_with(REMOTE_ADDR)
        limiter.resets_in.assert_called_once_with(REMOTE_ADDR)
        assert metrics.increment.call_args_list == [
            mocker.call("warehouse.authentication.recovery_code.start"),
            mocker.call(
                "warehouse.authentication.ratelimited",
                tags=["mechanism:check_recovery_code", "ratelimiter:ip"],
            ),
        ]

    def test_regenerate_recovery_codes(self, user_service):
        user = UserFactory.create()

        with pytest.raises(NoRecoveryCodes):
            user_service.get_recovery_codes(user.id)

        user_service.generate_recovery_codes(user.id)
        initial_codes = user_service.get_recovery_codes(user.id)

        assert len(initial_codes) == 8

        user_service.generate_recovery_codes(user.id)
        new_codes = user_service.get_recovery_codes(user.id)

        assert len(new_codes) == 8
        assert [c.id for c in initial_codes] != [c.id for c in new_codes]

    def test_get_password_timestamp(self, user_service):
        create_time = datetime.datetime.now(datetime.UTC)
        with freezegun.freeze_time(create_time):
            user = UserFactory.create()
            user.password_date = create_time

        assert user_service.get_password_timestamp(user.id) == create_time.timestamp()

    def test_get_password_timestamp_no_value(self, user_service):
        user = UserFactory.create()
        user.password_date = None

        assert user_service.get_password_timestamp(user.id) == 0

    def test_needs_tos_flash_no_engagements(self, user_service):
        user = UserFactory.create()
        assert user_service.needs_tos_flash(user.id, "initial") is True

    def test_needs_tos_flash_with_passive_engagements(self, user_service):
        user = UserFactory.create()
        assert user_service.needs_tos_flash(user.id, "initial") is True

        user_service.record_tos_engagement(
            user.id, "initial", TermsOfServiceEngagement.Notified
        )
        assert user_service.needs_tos_flash(user.id, "initial") is True

        user_service.record_tos_engagement(
            user.id, "initial", TermsOfServiceEngagement.Flashed
        )
        assert user_service.needs_tos_flash(user.id, "initial") is True

    def test_needs_tos_flash_with_viewed_engagement(self, user_service):
        user = UserFactory.create()
        assert user_service.needs_tos_flash(user.id, "initial") is True

        user_service.record_tos_engagement(
            user.id, "initial", TermsOfServiceEngagement.Viewed
        )
        assert user_service.needs_tos_flash(user.id, "initial") is False

    def test_needs_tos_flash_with_agreed_engagement(self, user_service):
        user = UserFactory.create()
        assert user_service.needs_tos_flash(user.id, "initial") is True

        user_service.record_tos_engagement(
            user.id, "initial", TermsOfServiceEngagement.Agreed
        )
        assert user_service.needs_tos_flash(user.id, "initial") is False

    def test_needs_tos_flash_if_engaged_more_than_30_days_ago(self, user_service):
        user = UserFactory.create()
        UserTermsOfServiceEngagementFactory.create(
            user=user,
            created=(datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=31)),
            engagement=TermsOfServiceEngagement.Notified,
        )
        assert user_service.needs_tos_flash(user.id, "initial") is False

    def test_record_tos_engagement_invalid_engagement(self, user_service):
        user = UserFactory.create()
        assert user.terms_of_service_engagements == []
        with pytest.raises(ValueError):  # noqa: PT011
            user_service.record_tos_engagement(
                user.id,
                "initial",
                None,
            )

    @pytest.mark.parametrize(
        "engagement",
        [
            TermsOfServiceEngagement.Flashed,
            TermsOfServiceEngagement.Notified,
            TermsOfServiceEngagement.Viewed,
            TermsOfServiceEngagement.Agreed,
        ],
    )
    def test_record_tos_engagement(self, user_service, db_request, engagement):
        user = UserFactory.create()
        assert user.terms_of_service_engagements == []
        user_service.record_tos_engagement(
            user.id,
            "initial",
            engagement,
        )
        assert (
            db_request.db.query(UserTermsOfServiceEngagement)
            .filter(
                UserTermsOfServiceEngagement.user_id == user.id,
                UserTermsOfServiceEngagement.revision == "initial",
                UserTermsOfServiceEngagement.engagement == engagement,
            )
            .count()
        ) == 1

    def test_get_account_associations(self, user_service):
        user = UserFactory.create()
        # Create multiple associations
        assoc1 = OAuthAccountAssociationFactory.create(
            user=user, service="github", external_user_id="123"
        )
        assoc2 = OAuthAccountAssociationFactory.create(
            user=user, service="github", external_user_id="456"
        )
        # Create association for different user (should not be returned)
        other_user = UserFactory.create()
        OAuthAccountAssociationFactory.create(user=other_user, service="github")

        associations = user_service.get_account_associations(str(user.id))

        assert len(associations) == 2
        # Verify both associations are returned (order may vary due to same timestamps)
        assoc_ids = {assoc.id for assoc in associations}
        assert assoc_ids == {assoc1.id, assoc2.id}

    def test_get_account_associations_empty(self, user_service):
        user = UserFactory.create()

        associations = user_service.get_account_associations(str(user.id))

        assert associations == []

    def test_get_account_association(self, user_service):
        user = UserFactory.create()
        assoc = OAuthAccountAssociationFactory.create(user=user)

        result = user_service.get_account_association(str(assoc.id))

        assert result is not None
        assert result.id == assoc.id
        assert result.user == user

    def test_get_account_association_not_found(self, user_service):
        result = user_service.get_account_association(str(uuid.uuid4()))

        assert result is None

    def test_get_account_association_by_service(self, user_service):
        user = UserFactory.create()
        assoc = OAuthAccountAssociationFactory.create(
            user=user, service="github", external_user_id="123"
        )
        # Create another association with different external_user_id
        OAuthAccountAssociationFactory.create(
            user=user, service="github", external_user_id="456"
        )

        result = user_service.get_account_association_by_oauth_service(
            str(user.id), "github", "123"
        )

        assert result is not None
        assert result.id == assoc.id
        assert result.external_user_id == "123"

    def test_get_account_association_by_service_not_found(self, user_service):
        user = UserFactory.create()

        result = user_service.get_account_association_by_oauth_service(
            str(user.id), "github", "999"
        )

        assert result is None

    def test_add_account_association_minimal(self, user_service):
        user = UserFactory.create()

        association = user_service.add_account_association(
            user_id=str(user.id),
            service="github",
            external_user_id="123",
            external_username="testuser",
        )

        assert association.id is not None
        assert association.user == user
        assert association.service == "github"
        assert association.external_user_id == "123"
        assert association.external_username == "testuser"
        # metadata_ defaults to empty dict
        assert association.metadata_ == {}

    def test_add_account_association_with_metadata(self, user_service):
        user = UserFactory.create()

        metadata = {"email": "test@example.com", "avatar_url": "https://..."}
        association = user_service.add_account_association(
            user_id=str(user.id),
            service="github",
            external_user_id="123",
            external_username="testuser",
            metadata=metadata,
        )

        assert association.metadata_ == metadata

    def test_add_account_association_duplicate(self, user_service):
        user1 = UserFactory.create()
        user2 = UserFactory.create()

        # User1 creates an association
        user_service.add_account_association(
            user_id=str(user1.id),
            service="github",
            external_user_id="123",
            external_username="testuser",
        )

        # User2 tries to associate the same external account - should raise ValueError
        with pytest.raises(ValueError, match="already associated"):
            user_service.add_account_association(
                user_id=str(user2.id),
                service="github",
                external_user_id="123",
                external_username="testuser",
            )

    def test_delete_account_association(self, user_service):
        user = UserFactory.create()
        assoc = OAuthAccountAssociationFactory.create(user=user)
        assoc_id = str(assoc.id)

        result = user_service.delete_account_association(assoc_id)

        assert result is True
        # Verify it's actually deleted
        assert user_service.get_account_association(assoc_id) is None

    def test_delete_account_association_not_found(self, user_service):
        result = user_service.delete_account_association(str(uuid.uuid4()))

        assert result is False


class TestTokenService:
    def test_verify_service(self):
        assert verifyClass(ITokenService, services.TokenService)

    def test_service_creation(self, mocker):
        serializer_cls = mocker.patch.object(
            services, "URLSafeTimedSerializer", autospec=True
        )

        service = services.TokenService("secret", "salt", 60)

        assert service.serializer is serializer_cls.return_value
        assert service.max_age == 60
        serializer_cls.assert_called_once_with("secret", salt="salt")

    def test_dumps(self, token_service):
        assert token_service.dumps({"foo": "bar"})

    def test_loads(self, token_service):
        token = token_service.dumps({"foo": "bar"})
        assert token_service.loads(token) == {"foo": "bar"}

    def test_loads_return_timestamp(self, token_service):
        sign_time = datetime.datetime.now(datetime.UTC)
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
        now = datetime.datetime.now(datetime.UTC)

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

    def test_unsafe_load_payload(self, token_service):
        sign_time = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
        with freezegun.freeze_time(sign_time):
            token = token_service.dumps({"foo": "bar"})

        with pytest.raises(TokenExpired):
            token_service.loads(token)

        assert token_service.unsafe_load_payload(token) == {"foo": "bar"}

    def test_unsafe_load_payload_signature_invalid(self, token_service):
        sign_time = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=10)
        with freezegun.freeze_time(sign_time):
            token = services.TokenService("wrongsecret", "pepper", max_age=3600).dumps(
                {"foo": "bar"}
            )

        with pytest.raises(TokenInvalid):
            token_service.loads(token)

        assert token_service.unsafe_load_payload(token) is None


def test_database_login_factory(db_request, pyramid_services, metrics, mocker):
    service_cls = mocker.patch.object(services, "DatabaseUserService", autospec=True)
    ratelimiters = {
        name: DummyRateLimiter()
        for name in (
            "global.login",
            "user.login",
            "ip.login",
            "email.add",
            "password.reset",
            "2fa.user",
            "2fa.ip",
        )
    }
    for name, limiter in ratelimiters.items():
        pyramid_services.register_service(limiter, IRateLimiter, None, name=name)

    assert (
        services.database_login_factory(mocker.sentinel.context, db_request)
        is service_cls.return_value
    )
    service_cls.assert_called_once_with(
        db_request.db,
        metrics=metrics,
        remote_addr=REMOTE_ADDR,
        ratelimiters=ratelimiters,
    )


@pytest.mark.parametrize("custom_max_age", [False, True])
def test_token_service_factory_max_age(pyramid_request, mocker, custom_max_age):
    name = "name"
    service_cls = mocker.create_autospec(services.TokenService)

    service_factory = services.TokenServiceFactory(name, service_cls)

    assert service_factory.name == name
    assert service_factory.service_class == service_cls

    pyramid_request.registry.settings.update(
        {
            "token.name.secret": mocker.sentinel.secret,
            "token.default.max_age": mocker.sentinel.default_max_age,
        }
    )
    if custom_max_age:
        pyramid_request.registry.settings["token.name.max_age"] = (
            mocker.sentinel.custom_max_age
        )

    assert (
        service_factory(mocker.sentinel.context, pyramid_request)
        is service_cls.return_value
    )
    service_cls.assert_called_once_with(
        mocker.sentinel.secret,
        name,
        (
            mocker.sentinel.custom_max_age
            if custom_max_age
            else mocker.sentinel.default_max_age
        ),
    )


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
    @responses.activate
    def test_success(self, http_session, password, prefix, expected, dataset):
        url = f"https://api.pwnedpasswords.com/range/{prefix}"
        responses.add(responses.GET, url, body=dataset)

        svc = services.HaveIBeenPwnedPasswordBreachedService(
            session=http_session, metrics=NullMetrics()
        )

        assert svc.check_password(password) == expected
        http_session.get.assert_called_once_with(url)

    @responses.activate
    def test_failure(self, http_session):
        class AnError(Exception):
            pass

        responses.add(
            responses.GET,
            "https://api.pwnedpasswords.com/range/a2f8f",
            body=AnError(),
        )

        svc = services.HaveIBeenPwnedPasswordBreachedService(
            session=http_session, metrics=NullMetrics()
        )

        with pytest.raises(AnError):
            svc.check_password("my password")

    @responses.activate
    def test_http_failure(self, http_session):
        responses.add(
            responses.GET,
            "https://api.pwnedpasswords.com/range/a2f8f",
            status=500,
        )

        svc = services.HaveIBeenPwnedPasswordBreachedService(
            session=http_session, metrics=NullMetrics()
        )
        assert not svc.check_password("my password")
        http_session.get.assert_called_once_with(
            "https://api.pwnedpasswords.com/range/a2f8f"
        )

    def test_metrics_increments(self, metrics, mocker):
        svc = services.HaveIBeenPwnedPasswordBreachedService(
            session=mocker.sentinel.session, metrics=metrics
        )

        svc._metrics_increment("something")
        svc._metrics_increment("another_thing")
        svc._metrics_increment("something")

        assert metrics.increment.call_args_list == [
            mocker.call("something"),
            mocker.call("another_thing"),
            mocker.call("something"),
        ]

    def test_factory(self, pyramid_request, metrics, mocker):
        pyramid_request.http = mocker.sentinel.http
        pyramid_request.help_url = mocker.Mock(
            side_effect=lambda _anchor=None: f"http://localhost/help/#{_anchor}"
        )
        svc = services.HaveIBeenPwnedPasswordBreachedService.create_service(
            mocker.sentinel.context, pyramid_request
        )

        assert svc._http is pyramid_request.http
        assert svc._metrics is metrics
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
    def test_failure_message(self, pyramid_request, mocker, help_url, expected):
        pyramid_request.http = mocker.sentinel.http
        pyramid_request.help_url = mocker.Mock(return_value=help_url)
        svc = services.HaveIBeenPwnedPasswordBreachedService.create_service(
            mocker.sentinel.context, pyramid_request
        )
        assert svc.failure_message == expected


class TestNullPasswordBreachedService:
    def test_verify_service(self):
        assert verifyClass(
            IPasswordBreachedService, services.NullPasswordBreachedService
        )

    def test_check_password(self):
        svc = services.NullPasswordBreachedService()
        assert not svc.check_password("password")

    def test_factory(self, pyramid_request, mocker):
        svc = services.NullPasswordBreachedService.create_service(
            mocker.sentinel.context, pyramid_request
        )

        assert isinstance(svc, services.NullPasswordBreachedService)
        assert not svc.check_password("hunter2")


class TestHaveIBeenPwnedEmailBreachedService:
    def test_verify_service(self):
        assert verifyClass(
            IEmailBreachedService, services.HaveIBeenPwnedEmailBreachedService
        )

    def test_no_api_key(self, mocker):
        svc = services.HaveIBeenPwnedEmailBreachedService(
            session=mocker.sentinel.session
        )
        assert svc.get_email_breach_count("anything") is None

    @pytest.mark.parametrize(
        ("address", "response_kwargs", "expected"),
        [
            ("foo@example.com", {"json": [{"Name": "LinkedIn"}]}, 1),
            ("new-email@gmail.com", {"status": 404}, 0),
            ("invalid-address", {"status": 401}, -1),
        ],
    )
    @responses.activate
    def test_breach_count(self, http_session, address, response_kwargs, expected):
        url = f"https://haveibeenpwned.com/api/v3/breachedaccount/{address}"
        responses.add(responses.GET, url, **response_kwargs)
        svc = services.HaveIBeenPwnedEmailBreachedService(
            session=http_session, api_key="blowhole"
        )

        assert svc.get_email_breach_count(address) == expected
        http_session.get.assert_called_once_with(
            url,
            headers={"User-Agent": "PyPI.org", "hibp-api-key": "blowhole"},
            timeout=(0.25, 0.25),
        )

    def test_factory(self, pyramid_request, mocker):
        pyramid_request.http = mocker.sentinel.http
        pyramid_request.registry.settings["hibp.api_key"] = "blowhole"
        svc = services.HaveIBeenPwnedEmailBreachedService.create_service(
            mocker.sentinel.context, pyramid_request
        )

        assert svc._http is pyramid_request.http
        assert svc.api_key == "blowhole"


class TestNullEmailBreachedService:
    def test_verify_service(self):
        assert verifyClass(IEmailBreachedService, services.NullEmailBreachedService)

    def test_check_email(self):
        svc = services.NullEmailBreachedService()
        assert svc.get_email_breach_count("foo@example.com") == 0

    def test_factory(self, pyramid_request, mocker):
        svc = services.NullEmailBreachedService.create_service(
            mocker.sentinel.context, pyramid_request
        )

        assert isinstance(svc, services.NullEmailBreachedService)
        assert svc.get_email_breach_count("foo@example.com") == 0


class TestNullDomainStatusService:
    def test_verify_service(self):
        assert verifyClass(IDomainStatusService, services.NullDomainStatusService)

    def test_get_domain_status(self):
        svc = services.NullDomainStatusService()
        assert svc.get_domain_status("example.com") == ["active"]

    def test_factory(self, pyramid_request, mocker):
        svc = services.NullDomainStatusService.create_service(
            mocker.sentinel.context, pyramid_request
        )

        assert isinstance(svc, services.NullDomainStatusService)
        assert svc.get_domain_status("example.com") == ["active"]


class TestDomainrDomainStatusService:
    URL = "https://api.domainr.com/v2/status"

    def test_verify_service(self):
        assert verifyClass(IDomainStatusService, services.DomainrDomainStatusService)

    @pytest.mark.parametrize(
        ("domain", "response_kwargs", "expected"),
        [
            pytest.param(
                "example.com",
                {
                    "json": {
                        "status": [
                            {"domain": "example.com", "status": "undelegated inactive"}
                        ]
                    }
                },
                ["undelegated", "inactive"],
                id="success",
            ),
            pytest.param("example.com", {"status": 400}, None, id="http-error"),
            pytest.param(
                "example.ocm",
                {
                    "json": {
                        "status": [],
                        "errors": [
                            {
                                "code": 400,
                                "detail": "unknown zone: ocm",
                                "message": "Bad request",
                            }
                        ],
                    }
                },
                None,
                id="response-contains-errors",
            ),
        ],
    )
    @responses.activate
    def test_get_domain_status(self, http_session, domain, response_kwargs, expected):
        responses.add(responses.GET, self.URL, **response_kwargs)
        svc = services.DomainrDomainStatusService(
            session=http_session, client_id="some_client_id"
        )

        assert svc.get_domain_status(domain) == expected
        http_session.get.assert_called_once_with(
            self.URL,
            params={"client_id": "some_client_id", "domain": domain},
            timeout=5,
        )

    def test_factory(self, pyramid_request, mocker):
        pyramid_request.http = mocker.sentinel.http
        pyramid_request.registry.settings["domain_status.client_id"] = "some_client_id"
        svc = services.DomainrDomainStatusService.create_service(
            mocker.sentinel.context, pyramid_request
        )

        assert svc._http is pyramid_request.http
        assert svc.client_id == "some_client_id"


class TestFastlyDomainStatusService:
    URL = "https://api.fastly.com/domain-management/v1/tools/status"

    def test_verify_service(self):
        assert verifyClass(IDomainStatusService, services.FastlyDomainStatusService)

    @pytest.mark.parametrize(
        ("domain", "response_kwargs", "expected"),
        [
            pytest.param(
                "example.com",
                {
                    "json": {
                        "domain": "example.com",
                        "zone": "com",
                        "status": "undelegated inactive",
                        "tags": "generic",
                    }
                },
                ["undelegated", "inactive"],
                id="success",
            ),
            pytest.param("example.com", {"status": 400}, None, id="http-error"),
            pytest.param(
                "example.ocm",
                {
                    "json": {
                        "errors": [
                            {
                                "code": 404,
                                "message": "Domain not found",
                                "detail": "example.ocm",
                            }
                        ],
                    }
                },
                None,
                id="response-contains-errors",
            ),
        ],
    )
    @responses.activate
    def test_get_domain_status(self, http_session, domain, response_kwargs, expected):
        responses.add(responses.GET, self.URL, **response_kwargs)
        svc = services.FastlyDomainStatusService(
            session=http_session, api_key="some_api_key"
        )

        assert svc.get_domain_status(domain) == expected
        http_session.get.assert_called_once_with(
            self.URL,
            params={"domain": domain},
            headers={"Fastly-Key": "some_api_key"},
            timeout=5,
        )

    def test_factory(self, pyramid_request, mocker):
        pyramid_request.http = mocker.sentinel.http
        pyramid_request.registry.settings["domain_status.api_key"] = "some_api_key"
        svc = services.FastlyDomainStatusService.create_service(
            mocker.sentinel.context, pyramid_request
        )

        assert svc._http is pyramid_request.http
        assert svc.api_key == "some_api_key"


class TestNullEmailReputationService:
    def test_verify_service(self):
        assert verifyClass(IEmailReputationService, services.NullEmailReputationService)

    def test_check_email_returns_no_signals(self):
        svc = services.NullEmailReputationService()

        result = svc.check_email("foo@example.com")

        assert result == EmailReputationResult()
        assert result.signals == []
        assert not result.should_block

    def test_factory(self):
        svc = services.NullEmailReputationService.create_service(None, None)

        assert isinstance(svc, services.NullEmailReputationService)
        assert svc.check_email("foo@example.com").signals == []


class TestEmailReputationResult:
    DOMAIN_VERDICT = {
        "disposable": True,
        "public_domain": False,
        "relay_domain": False,
        "disposable_provider": "DropMail",
    }

    @pytest.mark.parametrize(
        ("result_kwargs", "expected"),
        [
            pytest.param(DOMAIN_VERDICT, True, id="named-provider-with-clear-flags"),
            pytest.param(
                DOMAIN_VERDICT | {"disposable_provider": None},
                False,
                id="throwaway-address-on-unnamed-domain",
            ),
            pytest.param(
                DOMAIN_VERDICT | {"public_domain": True}, False, id="public-domain"
            ),
            pytest.param(
                DOMAIN_VERDICT | {"relay_domain": True}, False, id="relay-domain"
            ),
            pytest.param({"disposable": True}, False, id="unknown-flags"),
            pytest.param(
                DOMAIN_VERDICT | {"disposable": False}, False, id="not-disposable"
            ),
        ],
    )
    def test_disposable_domain_requires_provider_and_explicit_flags(
        self, result_kwargs, expected
    ):
        result = EmailReputationResult(**result_kwargs)

        assert result.disposable_domain is expected


class TestUserCheckEmailReputationService:
    def test_verify_service(self):
        assert verifyClass(
            IEmailReputationService,
            services.UserCheckEmailReputationService,
        )

    def test_factory(self):
        ratelimiter = object()

        def _find_service(iface, name=None, context=None):
            return {(IRateLimiter, "email.reputation"): ratelimiter}[(iface, name)]

        request = SimpleNamespace(
            http=object(),
            metrics=object(),
            registry=SimpleNamespace(
                settings={"email_reputation.api_key": "some_api_key"}
            ),
            find_service=_find_service,
            remote_addr=REMOTE_ADDR,
            user=None,
        )
        svc = services.UserCheckEmailReputationService.create_service(None, request)

        assert svc._http is request.http
        assert svc._metrics is request.metrics
        assert svc._ratelimiter is ratelimiter
        assert svc._ratelimit_key == REMOTE_ADDR
        assert svc.api_key == "some_api_key"

    def test_factory_keys_the_budget_on_an_authenticated_caller(self, db_session):
        """
        An identified caller is charged by user id, so one signed-in account
        cannot spend the budget of everyone sharing its egress address.
        """
        user = UserFactory.create()
        ratelimiter = object()

        request = SimpleNamespace(
            http=object(),
            metrics=object(),
            registry=SimpleNamespace(
                settings={"email_reputation.api_key": "some_api_key"}
            ),
            find_service=lambda iface, name=None, context=None: ratelimiter,
            remote_addr=REMOTE_ADDR,
            user=user,
        )
        svc = services.UserCheckEmailReputationService.create_service(None, request)

        assert svc._ratelimit_key == str(user.id)

    def _response(self, mocker, body):
        response = mocker.Mock(spec=requests.Response)
        response.json.return_value = body
        return response

    def _service(
        self,
        mocker,
        response,
        metrics=None,
        ratelimiter=None,
        ratelimit_key=REMOTE_ADDR,
    ):
        session = requests.Session()
        mocker.patch.object(session, "get", autospec=True, return_value=response)
        return (
            services.UserCheckEmailReputationService(
                session=session,
                api_key="some_api_key",
                metrics=metrics if metrics is not None else NullMetrics(),
                ratelimiter=(
                    ratelimiter if ratelimiter is not None else DummyRateLimiter()
                ),
                ratelimit_key=ratelimit_key,
            ),
            session,
        )

    def test_disposable_domain(self, mocker, ratelimit_service):
        svc, session = self._service(
            mocker,
            self._response(
                mocker,
                {
                    "status": 200,
                    "email": "foo@dropmail.me",
                    "domain": "dropmail.me",
                    "mx": True,
                    "disposable": True,
                    "disposable_provider": "DropMail",
                    "public_domain": False,
                    "relay_domain": False,
                    "spam": False,
                    "blocklisted": False,
                },
            ),
            ratelimiter=ratelimit_service,
        )

        result = svc.check_email("foo@dropmail.me")

        assert result == EmailReputationResult(
            mx=True,
            disposable=True,
            public_domain=False,
            relay_domain=False,
            spam=False,
            blocklisted=False,
            disposable_provider="DropMail",
        )
        assert result.signals == ["disposable"]
        assert result.disposable_domain
        session.get.assert_called_once_with(
            "https://api.usercheck.com/email/foo%40dropmail.me",
            headers={"Authorization": "Bearer some_api_key"},
            timeout=(0.25, 1),
        )
        # The budget is spent atomically, before the remote call.
        ratelimit_service.hit.assert_called_once_with(REMOTE_ADDR)

    def test_disposable_address_on_public_domain(self, mocker):
        """
        A throwaway alias on a public provider reports disposable for the
        address, without implicating the domain itself.
        """
        svc, _session = self._service(
            mocker,
            self._response(
                mocker,
                {
                    "email": "throwaway@gmail.com",
                    "domain": "gmail.com",
                    "disposable": True,
                    "public_domain": True,
                },
            ),
        )

        result = svc.check_email("throwaway@gmail.com")

        assert result.should_block
        assert not result.disposable_domain
        assert result.disposable_provider is None

    def test_clean_address(self, mocker):
        svc, _session = self._service(
            mocker,
            self._response(
                mocker,
                {
                    "status": 200,
                    "email": "foo@python.org",
                    "domain": "python.org",
                    "mx": True,
                    "disposable": False,
                    "public_domain": False,
                    "relay_domain": False,
                    "spam": False,
                    "blocklisted": False,
                },
            ),
        )

        result = svc.check_email("foo@python.org")

        assert result.signals == []
        assert not result.should_block

    def test_multiple_signals_are_reported(self, mocker):
        svc, _session = self._service(
            mocker,
            self._response(
                mocker,
                {
                    "domain": "example.com",
                    "mx": False,
                    "disposable": True,
                    "public_domain": True,
                    "relay_domain": True,
                    "spam": True,
                    "blocklisted": True,
                },
            ),
        )

        result = svc.check_email("foo@example.com")

        assert result.signals == [
            "blocklisted",
            "disposable",
            "no_mx",
            "public_domain",
            "relay_domain",
            "spam",
        ]

    def test_missing_keys_are_unknown_signals(self, mocker):
        """
        Keys absent from the response are unknown, not clear, so they can
        neither block nor escalate.
        """
        svc, _session = self._service(mocker, self._response(mocker, {}))

        result = svc.check_email("foo@Example.COM")

        assert result == EmailReputationResult()
        assert result.signals == []
        assert not result.should_block
        assert not result.disposable_domain

    def test_non_boolean_signals_are_unknown(self, mocker):
        """
        Type drift upstream ("false" as a string is truthy) must read as
        unknown rather than as a signal.
        """
        svc, _session = self._service(
            mocker,
            self._response(
                mocker,
                {
                    "domain": "example.com",
                    "disposable": "false",
                    "public_domain": "true",
                },
            ),
        )

        result = svc.check_email("foo@example.com")

        assert result.disposable is None
        assert result.public_domain is None
        assert not result.should_block
        assert not result.disposable_domain

    def test_the_full_address_is_sent_quoted(self, mocker):
        """
        The /email/ endpoint evaluates the specific address, so the whole
        address goes into the URL path, percent-encoded. That includes "/",
        which is valid in a local part and would otherwise split the path
        and fail the check open.
        """
        svc, session = self._service(
            mocker,
            self._response(mocker, {"domain": "example.com", "disposable": False}),
        )

        svc.check_email("foo/bar+tag@example.com")

        (url,) = session.get.call_args.args
        assert url == "https://api.usercheck.com/email/foo%2Fbar%2Btag%40example.com"

    @pytest.mark.parametrize("status_code", [400, 401, 429, 500])
    def test_http_error_fails_open_after_spending_budget(
        self, metrics, mocker, ratelimit_service, status_code
    ):
        response = self._response(mocker, None)
        response.raise_for_status.side_effect = requests.HTTPError(
            response=SimpleNamespace(status_code=status_code)
        )
        svc, _session = self._service(
            mocker, response, metrics=metrics, ratelimiter=ratelimit_service
        )

        assert svc.check_email("foo@example.com") is None
        # The budget is spent atomically before the remote call, so a
        # repeatedly failing upstream still consumes it -- bounding how
        # hard we hammer a failing service.
        ratelimit_service.hit.assert_called_once_with(REMOTE_ADDR)
        metrics.increment.assert_any_call(
            "warehouse.email_reputation.request",
            tags=[
                "service:usercheck",
                "result:error",
                f"status_code:{status_code}",
                "error_type:HTTPError",
            ],
        )

    @pytest.mark.parametrize(
        ("exc", "error_type"),
        [
            (requests.ConnectionError("no route to host"), "ConnectionError"),
            (requests.ConnectTimeout("timed out"), "ConnectTimeout"),
            (requests.ReadTimeout("timed out"), "ReadTimeout"),
        ],
    )
    def test_transport_error_fails_open(self, metrics, mocker, exc, error_type):
        """
        A failure below the HTTP layer never has a status code to report, so
        the exception type is what separates them: a connect timeout means we
        never reached UserCheck, a read timeout means we did and paid for a
        call we then discarded.
        """
        svc, session = self._service(mocker, None, metrics=metrics)
        session.get.side_effect = exc

        assert svc.check_email("foo@example.com") is None
        assert metrics.increment.call_args_list == [
            mocker.call(
                "warehouse.email_reputation.request",
                tags=[
                    "service:usercheck",
                    "result:error",
                    "status_code:none",
                    f"error_type:{error_type}",
                ],
            )
        ]

    def test_malformed_response_fails_open(self, metrics, mocker):
        response = self._response(mocker, None)
        response.json.side_effect = requests.exceptions.JSONDecodeError("", "", 0)
        svc, _session = self._service(mocker, response, metrics=metrics)

        assert svc.check_email("foo@example.com") is None
        assert metrics.increment.call_args_list == [
            mocker.call(
                "warehouse.email_reputation.request",
                tags=["service:usercheck", "result:invalid_response"],
            )
        ]

    def test_non_object_response_fails_open(self, metrics, mocker):
        svc, _session = self._service(
            mocker, self._response(mocker, ["not", "an", "object"]), metrics=metrics
        )

        assert svc.check_email("foo@example.com") is None
        assert metrics.increment.call_args_list == [
            mocker.call(
                "warehouse.email_reputation.request",
                tags=["service:usercheck", "result:invalid_response"],
            )
        ]

    def test_metrics_for_successful_check(self, metrics, mocker):
        svc, _session = self._service(
            mocker,
            self._response(
                mocker, {"domain": "dropmail.me", "disposable": True, "spam": True}
            ),
            metrics=metrics,
        )

        svc.check_email("foo@dropmail.me")

        assert metrics.increment.call_args_list == [
            mocker.call(
                "warehouse.email_reputation.request",
                tags=["service:usercheck", "result:success"],
            ),
            mocker.call(
                "warehouse.email_reputation.signal",
                tags=["service:usercheck", "signal:disposable"],
            ),
            mocker.call(
                "warehouse.email_reputation.signal",
                tags=["service:usercheck", "signal:spam"],
            ),
        ]

    def test_rate_limited_raises_instead_of_failing_open(
        self, metrics, mocker, ratelimit_service
    ):
        """
        The limiter is keyed on the caller's own address, so a client that
        could exhaust it at will could otherwise skip the very check that
        gates their own submissions. No remote call is made: hit() is an
        atomic test-and-set, and a denied hit consumes nothing further.
        """
        resets_in = datetime.timedelta(minutes=10)
        mocker.patch.object(ratelimit_service, "hit", return_value=False)
        mocker.patch.object(ratelimit_service, "resets_in", return_value=resets_in)
        svc, session = self._service(
            mocker, None, metrics=metrics, ratelimiter=ratelimit_service
        )

        with pytest.raises(TooManyEmailReputationChecks) as excinfo:
            svc.check_email("foo@example.com")

        assert excinfo.value.resets_in == resets_in
        session.get.assert_not_called()
        ratelimit_service.hit.assert_called_once_with(REMOTE_ADDR)
        assert metrics.increment.call_args_list == [
            mocker.call(
                "warehouse.email_reputation.request",
                tags=["service:usercheck", "result:ratelimited"],
            )
        ]

    @pytest.mark.parametrize("ratelimit_key", [None, ""])
    def test_missing_ratelimit_key_skips_the_ratelimiter(
        self, mocker, ratelimit_service, ratelimit_key
    ):
        """
        Without anything to name the caller there is no per-caller budget to
        spend, so the check proceeds instead of pooling every request into
        one shared bucket keyed on None or the empty string.
        """
        mocker.patch.object(ratelimit_service, "hit", return_value=False)
        svc, session = self._service(
            mocker,
            self._response(mocker, {"domain": "example.com"}),
            ratelimiter=ratelimit_service,
            ratelimit_key=ratelimit_key,
        )

        result = svc.check_email("foo@example.com")

        assert result == EmailReputationResult()
        ratelimit_service.hit.assert_not_called()
        session.get.assert_called_once()

    def test_no_api_key_fails_open_without_request(self, metrics, mocker):
        # If we haven't configured an API key, don't bother the remote service.
        svc, session = self._service(mocker, None, metrics=metrics)
        svc.api_key = None

        assert svc.check_email("foo@example.com") is None
        session.get.assert_not_called()
        assert metrics.increment.call_args_list == [
            mocker.call(
                "warehouse.email_reputation.request",
                tags=["service:usercheck", "result:not_configured"],
            )
        ]


class TestDeviceIsKnown:
    @pytest.fixture
    def device_request(self, db_request, pyramid_services, token_service, mocker):
        mocker.patch.object(
            token_service, "dumps", autospec=True, return_value="fake_token"
        )
        pyramid_services.register_service(
            token_service, ITokenService, None, name="confirm_login"
        )
        db_request.headers["User-Agent"] = (
            "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:15.0) "
            "Gecko/20100101 Firefox/15.0.1"
        )
        return db_request

    def _new_device_events(self, user_service, user):
        """The user's recorded LoginNewDevice events."""
        return (
            user_service.db.query(User.Event)
            .filter(
                User.Event.source_id == user.id,
                User.Event.tag == EventTag.Account.LoginNewDevice,
            )
            .all()
        )

    def test_device_is_known(self, user_service, device_request):
        user = UserFactory.create()
        UserUniqueLoginFactory.create(
            user=user, ip_address=device_request.ip_address, status="confirmed"
        )
        assert user_service.device_is_known(user.id, device_request)

    def test_device_is_not_known(self, user_service, mocker, device_request):
        user = UserFactory.create(with_verified_primary_email=True)
        send_email = mocker.patch.object(services, "send_unrecognized_login_email")

        assert not user_service.device_is_known(user.id, device_request)

        unique_login = (
            user_service.db.query(services.UserUniqueLogin)
            .filter(
                services.UserUniqueLogin.user_id == user.id,
                services.UserUniqueLogin.ip_address.has(ip_address=REMOTE_ADDR),
            )
            .one()
        )
        assert unique_login.expires is not None

        # A new device has no valid token outstanding, so no throttling
        send_email.assert_called_once_with(
            device_request,
            user,
            ip_address=REMOTE_ADDR,
            user_agent="Firefox (Ubuntu)",
            token="fake_token",
            repeat_window=None,
        )

    @pytest.mark.parametrize("two_factor_method", ["totp", "recovery-code"])
    def test_device_is_not_known_records_event(
        self, user_service, two_factor_method, mocker, device_request
    ):
        user = UserFactory.create(with_verified_primary_email=True)
        mocker.patch.object(services, "send_unrecognized_login_email")

        assert not user_service.device_is_known(
            user.id, device_request, two_factor_method=two_factor_method
        )

        # Verify a LoginNewDevice event was recorded with the 2FA method
        events = self._new_device_events(user_service, user)
        assert len(events) == 1
        assert events[0].ip_address == device_request.ip_address
        assert events[0].additional["two_factor_method"] == two_factor_method

    def test_device_is_known_does_not_record_new_device_event(
        self, user_service, device_request
    ):

        user = UserFactory.create()
        UserUniqueLoginFactory.create(
            user=user, ip_address=device_request.ip_address, status="confirmed"
        )
        assert user_service.device_is_known(user.id, device_request)

        # Verify no LoginNewDevice event was recorded
        assert self._new_device_events(user_service, user) == []

    def test_device_is_pending_not_expired_resends_email(
        self, user_service, device_request, mocker
    ):
        user = UserFactory.create(with_verified_primary_email=True)
        unique_login = UserUniqueLoginFactory.create(
            user=user,
            ip_address=device_request.ip_address,
            status="pending",
            # A future expiry, as device_is_known always sets on pending logins
            expires=datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1),
        )
        original_expires = unique_login.expires
        send_email = mocker.patch.object(services, "send_unrecognized_login_email")

        assert not user_service.device_is_known(user.id, device_request)
        # The pending login's expiry is untouched, but the email is re-sent,
        # throttled by the email's own repeat_window since the earlier
        # email's token still works (hence no repeat_window override here).
        assert unique_login.expires == original_expires
        send_email.assert_called_once_with(
            device_request,
            user,
            ip_address=REMOTE_ADDR,
            user_agent="Firefox (Ubuntu)",
            token="fake_token",
        )

        # A repeat attempt from a known-but-pending device is not a new device
        assert self._new_device_events(user_service, user) == []

    def test_device_is_pending_and_expired(self, user_service, device_request, mocker):
        user = UserFactory.create(with_verified_primary_email=True)
        UserUniqueLoginFactory.create(
            user=user,
            status="pending",
            ip_address=device_request.ip_address,
            created=datetime.datetime(1970, 1, 1),
            expires=datetime.datetime(1970, 1, 1),
        )
        send_email = mocker.patch.object(services, "send_unrecognized_login_email")

        assert not user_service.device_is_known(user.id, device_request)
        # A lapsed confirmation window invalidated the earlier token, so the
        # fresh email must not be throttled
        send_email.assert_called_once_with(
            device_request,
            user,
            ip_address=REMOTE_ADDR,
            user_agent="Firefox (Ubuntu)",
            token="fake_token",
            repeat_window=None,
        )

    @pytest.mark.parametrize("ua_string", [None, "no bueno", "Python-urllib/3.7"])
    def test_device_is_not_known_bad_user_agent(
        self, user_service, ua_string, mocker, device_request
    ):
        user = UserFactory.create(with_verified_primary_email=True)
        send_email = mocker.patch.object(services, "send_unrecognized_login_email")
        if ua_string:
            device_request.headers["User-Agent"] = ua_string
        else:
            del device_request.headers["User-Agent"]

        assert not user_service.device_is_known(user.id, device_request)
        send_email.assert_called_once_with(
            device_request,
            user,
            ip_address=REMOTE_ADDR,
            user_agent=ua_string or "Unknown User-Agent",
            token="fake_token",
            repeat_window=None,
        )
