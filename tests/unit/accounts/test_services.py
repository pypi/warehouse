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
import uuid

import freezegun
import pretend
import pytest
import requests

from zope.interface.verify import verifyClass

from warehouse.accounts import services
from warehouse.accounts.interfaces import (
    IUserService,
    ITokenService,
    IPasswordBreachedService,
    TokenExpired,
    TokenInvalid,
    TokenMissing,
    TooManyFailedLogins,
)
from warehouse.accounts.models import DisableReason
from warehouse.metrics import IMetricsService, NullMetrics
from warehouse.rate_limiting.interfaces import IRateLimiter

from ...common.db.accounts import UserFactory, EmailFactory


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

        ratelimiters = {"user": pretend.stub(), "global": pretend.stub()}

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

    def test_find_userid_nonexistant_user(self, user_service):
        assert user_service.find_userid("my_username") is None

    def test_find_userid_existing_user(self, user_service):
        user = UserFactory.create()
        assert user_service.find_userid(user.username) == user.id

    def test_check_password_global_rate_limited(self, user_service, metrics):
        resets = pretend.stub()
        limiter = pretend.stub(test=lambda: False, resets_in=lambda: resets)
        user_service.ratelimiters["global"] = limiter

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

    def test_check_password_nonexistant_user(self, user_service, metrics):
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
        user_service.ratelimiters["user"] = limiter

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

    global_ratelimiter = pretend.stub()
    user_ratelimiter = pretend.stub()

    def find_service(iface, name=None, context=None):
        if iface != IRateLimiter and name is None:
            return pyramid_services.find_service(iface, context=context)

        assert iface is IRateLimiter
        assert context is None
        assert name in {"global.login", "user.login"}

        return (
            {"global.login": global_ratelimiter, "user.login": user_ratelimiter}
        ).get(name)

    context = pretend.stub()
    request = pretend.stub(db=pretend.stub(), find_service=find_service)

    assert services.database_login_factory(context, request) is service_obj
    assert service_cls.calls == [
        pretend.call(
            request.db,
            metrics=metrics,
            ratelimiters={"global": global_ratelimiter, "user": user_ratelimiter},
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
                    "This password appears in a breach or has been compromised and "
                    "cannot be used."
                ),
            ),
            (
                "http://localhost/help/#compromised-password",
                (
                    "This password appears in a breach or has been compromised and "
                    "cannot be used. See "
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
                    "This password appears in a breach or has been compromised and "
                    "cannot be used."
                ),
            ),
            (
                "http://localhost/help/#compromised-password",
                (
                    "This password appears in a breach or has been compromised and "
                    "cannot be used. See the FAQ entry at "
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
