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

import datetime
import uuid

import freezegun
import pretend
import pytest

from zope.interface.verify import verifyClass

from warehouse.accounts import services
from warehouse.accounts.interfaces import (
    IUserService, ITokenService, TokenExpired, TokenInvalid, TokenMissing,
    TooManyFailedLogins,
)
from warehouse.rate_limiting.interfaces import IRateLimiter

from ...common.db.accounts import UserFactory, EmailFactory


class TestDatabaseUserService:

    def test_verify_service(self):
        assert verifyClass(IUserService, services.DatabaseUserService)

    def test_service_creation(self, monkeypatch):
        crypt_context_obj = pretend.stub()
        crypt_context_cls = pretend.call_recorder(
            lambda **kwargs: crypt_context_obj
        )
        monkeypatch.setattr(services, "CryptContext", crypt_context_cls)

        session = pretend.stub()
        service = services.DatabaseUserService(session)

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
            ),
        ]

    def test_find_userid_nonexistant_user(self, user_service):
        assert user_service.find_userid("my_username") is None

    def test_find_userid_existing_user(self, user_service):
        user = UserFactory.create()
        assert user_service.find_userid(user.username) == user.id

    def test_check_password_global_rate_limited(self, user_service):
        resets = pretend.stub()
        limiter = pretend.stub(test=lambda: False, resets_in=lambda: resets)
        user_service.ratelimiters["global"] = limiter

        with pytest.raises(TooManyFailedLogins) as excinfo:
            user_service.check_password(uuid.uuid4(), None)

        assert excinfo.value.resets_in is resets

    def test_check_password_nonexistant_user(self, user_service):
        assert not user_service.check_password(uuid.uuid4(), None)

    def test_check_password_user_rate_limited(self, user_service):
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

    def test_check_password_invalid(self, user_service):
        user = UserFactory.create()
        user_service.hasher = pretend.stub(
            verify_and_update=pretend.call_recorder(
                lambda l, r: (False, None)
            ),
        )

        assert not user_service.check_password(user.id, "user password")
        assert user_service.hasher.verify_and_update.calls == [
            pretend.call("user password", user.password),
        ]

    def test_check_password_valid(self, user_service):
        user = UserFactory.create()
        user_service.hasher = pretend.stub(
            verify_and_update=pretend.call_recorder(lambda l, r: (True, None)),
        )

        assert user_service.check_password(user.id, "user password")
        assert user_service.hasher.verify_and_update.calls == [
            pretend.call("user password", user.password),
        ]

    def test_check_password_updates(self, user_service):
        user = UserFactory.create()
        password = user.password
        user_service.hasher = pretend.stub(
            verify_and_update=pretend.call_recorder(
                lambda l, r: (True, "new password")
            ),
        )

        assert user_service.check_password(user.id, "user password")
        assert user_service.hasher.verify_and_update.calls == [
            pretend.call("user password", password),
        ]
        assert user.password == "new password"

    def test_create_user(self, user_service):
        user = UserFactory.build()
        email = "foo@example.com"
        new_user = user_service.create_user(
            username=user.username,
            name=user.name,
            password=user.password,
            email=email
        )
        user_service.db.flush()
        user_from_db = user_service.get_user(new_user.id)
        assert user_from_db.username == user.username
        assert user_from_db.name == user.name
        assert user_from_db.email == email

    def test_update_user(self, user_service):
        user = UserFactory.create()
        new_name, password = "new username", "TestPa@@w0rd"
        user_service.update_user(user.id, username=new_name, password=password)
        user_from_db = user_service.get_user(user.id)
        assert user_from_db.username == user.username
        assert password != user_from_db.password
        assert user_service.hasher.verify(password, user_from_db.password)

    def test_verify_email(self, user_service):
        user = UserFactory.create()
        EmailFactory.create(user=user, primary=True,
                            verified=False)
        EmailFactory.create(user=user, primary=False,
                            verified=False)
        user_service.verify_email(user.id, user.emails[0].email)
        assert user.emails[0].verified
        assert not user.emails[1].verified

    def test_find_by_email(self, user_service):
        user = UserFactory.create()
        EmailFactory.create(user=user, primary=True, verified=False)

        found_userid = user_service.find_userid_by_email(user.emails[0].email)
        user_service.db.flush()

        assert user.id == found_userid

    def test_find_by_email_not_found(self, user_service):
        assert user_service.find_userid_by_email("something") is None

    def test_create_login_success(self, user_service):
        user = user_service.create_user(
            "test_user", "test_name", "test_password", "test_email")

        assert user.id is not None
        # now make sure that we can log in as that user
        assert user_service.check_password(user.id, "test_password")

    def test_create_login_error(self, user_service):
        user = user_service.create_user(
            "test_user", "test_name", "test_password", "test_email")

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
        assert serializer_cls.calls == [
            pretend.call(secret, salt=salt)
        ]

    def test_dumps(self, token_service):
        assert token_service.dumps({'foo': 'bar'})

    def test_loads(self, token_service):
        token = token_service.dumps({'foo': 'bar'})
        assert token_service.loads(token) == {'foo': 'bar'}

    @pytest.mark.parametrize('token', ['', None])
    def test_loads_token_is_none(self, token_service, token):
        with pytest.raises(TokenMissing):
            token_service.loads(token)

    def test_loads_token_is_expired(self, token_service):
        now = datetime.datetime.utcnow()

        with freezegun.freeze_time(now) as frozen_time:
            token = token_service.dumps({'foo': 'bar'})

            frozen_time.tick(
                delta=datetime.timedelta(seconds=token_service.max_age + 1),
            )

            with pytest.raises(TokenExpired):
                token_service.loads(token)

    def test_loads_token_is_invalid(self, token_service):
        with pytest.raises(TokenInvalid):
            token_service.loads("invalid")


def test_database_login_factory(monkeypatch):
    service_obj = pretend.stub()
    service_cls = pretend.call_recorder(
        lambda session, ratelimiters: service_obj,
    )
    monkeypatch.setattr(services, "DatabaseUserService", service_cls)

    global_ratelimiter = pretend.stub()
    user_ratelimiter = pretend.stub()

    def find_service(iface, name, context):
        assert iface is IRateLimiter
        assert context is None
        assert name in {"global.login", "user.login"}

        return ({
            "global.login": global_ratelimiter,
            "user.login": user_ratelimiter
        }).get(name)

    context = pretend.stub()
    request = pretend.stub(
        db=pretend.stub(),
        find_service=find_service,
    )

    assert services.database_login_factory(context, request) is service_obj
    assert service_cls.calls == [
        pretend.call(
            request.db,
            ratelimiters={
                "global": global_ratelimiter,
                "user": user_ratelimiter,
            },
        ),
    ]


def test_token_service_factory_default_max_age(monkeypatch):
    name = 'name'
    service_obj = pretend.stub()
    service_cls = pretend.call_recorder(lambda *args: service_obj)

    service_factory = services.TokenServiceFactory(name, service_cls)

    assert service_factory.name == name
    assert service_factory.service_class == service_cls

    context = pretend.stub()
    secret = pretend.stub()
    default_max_age = pretend.stub()
    request = pretend.stub(
        registry=pretend.stub(settings={
            'token.name.secret': secret,
            'token.default.max_age': default_max_age,
        })
    )

    assert service_factory(context, request) is service_obj
    assert service_cls.calls == [
        pretend.call(secret, name, default_max_age),
    ]


def test_token_service_factory_custom_max_age(monkeypatch):
    name = 'name'
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
        registry=pretend.stub(settings={
            'token.name.secret': secret,
            'token.default.max_age': default_max_age,
            'token.name.max_age': custom_max_age,
        })
    )

    assert service_factory(context, request) is service_obj
    assert service_cls.calls == [
        pretend.call(secret, name, custom_max_age),
    ]
