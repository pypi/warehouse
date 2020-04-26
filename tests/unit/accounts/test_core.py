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

import freezegun
import pretend
import pytest

from warehouse import accounts
from warehouse.accounts.interfaces import (
    IGitHubTokenScanningPayloadVerifyService,
    IPasswordBreachedService,
    ITokenService,
    IUserService,
)
from warehouse.accounts.models import DisableReason
from warehouse.accounts.services import (
    GitHubTokenScanningPayloadVerifyService,
    HaveIBeenPwnedPasswordBreachedService,
    TokenServiceFactory,
    database_login_factory,
)
from warehouse.errors import BasicAuthBreachedPassword
from warehouse.rate_limiting import IRateLimiter, RateLimit


class TestLogin:
    def test_invalid_route(self, pyramid_request, pyramid_services):
        service = pretend.stub(find_userid=pretend.call_recorder(lambda username: None))
        pyramid_services.register_service(service, IUserService, None)
        pyramid_services.register_service(
            pretend.stub(), IPasswordBreachedService, None
        )
        pyramid_request.matched_route = pretend.stub(name="route_name")
        assert accounts._basic_auth_login("myuser", "mypass", pyramid_request) is None
        assert service.find_userid.calls == []

    def test_with_no_user(self, pyramid_request, pyramid_services):
        service = pretend.stub(find_userid=pretend.call_recorder(lambda username: None))
        pyramid_services.register_service(service, IUserService, None)
        pyramid_services.register_service(
            pretend.stub(), IPasswordBreachedService, None
        )
        pyramid_request.matched_route = pretend.stub(name="forklift.legacy.file_upload")
        assert accounts._basic_auth_login("myuser", "mypass", pyramid_request) is None
        assert service.find_userid.calls == [pretend.call("myuser")]

    def test_with_invalid_password(self, pyramid_request, pyramid_services):
        user = pretend.stub(id=1)
        service = pretend.stub(
            get_user=pretend.call_recorder(lambda user_id: user),
            find_userid=pretend.call_recorder(lambda username: 1),
            check_password=pretend.call_recorder(
                lambda userid, password, tags=None: False
            ),
            is_disabled=pretend.call_recorder(lambda user_id: (False, None)),
        )
        pyramid_services.register_service(service, IUserService, None)
        pyramid_services.register_service(
            pretend.stub(), IPasswordBreachedService, None
        )
        pyramid_request.matched_route = pretend.stub(name="forklift.legacy.file_upload")
        assert accounts._basic_auth_login("myuser", "mypass", pyramid_request) is None
        assert service.find_userid.calls == [pretend.call("myuser")]
        assert service.get_user.calls == [pretend.call(1)]
        assert service.is_disabled.calls == [pretend.call(1)]
        assert service.check_password.calls == [
            pretend.call(1, "mypass", tags=["method:auth", "auth_method:basic"])
        ]

    def test_with_disabled_user_no_reason(self, pyramid_request, pyramid_services):
        user = pretend.stub(id=1)
        service = pretend.stub(
            get_user=pretend.call_recorder(lambda user_id: user),
            find_userid=pretend.call_recorder(lambda username: 1),
            check_password=pretend.call_recorder(
                lambda userid, password, tags=None: False
            ),
            is_disabled=pretend.call_recorder(lambda user_id: (True, None)),
        )
        pyramid_services.register_service(service, IUserService, None)
        pyramid_services.register_service(
            pretend.stub(), IPasswordBreachedService, None
        )
        pyramid_request.matched_route = pretend.stub(name="forklift.legacy.file_upload")
        assert accounts._basic_auth_login("myuser", "mypass", pyramid_request) is None
        assert service.find_userid.calls == [pretend.call("myuser")]
        assert service.get_user.calls == [pretend.call(1)]
        assert service.is_disabled.calls == [pretend.call(1)]
        assert service.check_password.calls == [
            pretend.call(1, "mypass", tags=["method:auth", "auth_method:basic"])
        ]

    def test_with_disabled_user_compromised_pw(self, pyramid_request, pyramid_services):
        user = pretend.stub(id=1)
        service = pretend.stub(
            get_user=pretend.call_recorder(lambda user_id: user),
            find_userid=pretend.call_recorder(lambda username: 1),
            check_password=pretend.call_recorder(
                lambda userid, password, tags=None: False
            ),
            is_disabled=pretend.call_recorder(
                lambda user_id: (True, DisableReason.CompromisedPassword)
            ),
        )
        pyramid_services.register_service(service, IUserService, None)
        pyramid_services.register_service(
            pretend.stub(failure_message_plain="Bad Password!"),
            IPasswordBreachedService,
            None,
        )
        pyramid_request.matched_route = pretend.stub(name="forklift.legacy.file_upload")

        with pytest.raises(BasicAuthBreachedPassword) as excinfo:
            assert (
                accounts._basic_auth_login("myuser", "mypass", pyramid_request) is None
            )

        assert excinfo.value.status == "401 Bad Password!"
        assert service.find_userid.calls == [pretend.call("myuser")]
        assert service.get_user.calls == [pretend.call(1)]
        assert service.is_disabled.calls == [pretend.call(1)]
        assert service.check_password.calls == []

    def test_with_valid_password(self, monkeypatch, pyramid_request, pyramid_services):
        principals = pretend.stub()
        authenticate = pretend.call_recorder(lambda userid, request: principals)
        monkeypatch.setattr(accounts, "_authenticate", authenticate)

        user = pretend.stub(id=2)
        service = pretend.stub(
            get_user=pretend.call_recorder(lambda user_id: user),
            find_userid=pretend.call_recorder(lambda username: 2),
            check_password=pretend.call_recorder(
                lambda userid, password, tags=None: True
            ),
            update_user=pretend.call_recorder(lambda userid, last_login: None),
            is_disabled=pretend.call_recorder(lambda user_id: (False, None)),
        )
        breach_service = pretend.stub(
            check_password=pretend.call_recorder(lambda pw, tags=None: False)
        )

        pyramid_services.register_service(service, IUserService, None)
        pyramid_services.register_service(
            breach_service, IPasswordBreachedService, None
        )

        pyramid_request.matched_route = pretend.stub(name="forklift.legacy.file_upload")

        now = datetime.datetime.utcnow()

        with freezegun.freeze_time(now):
            assert (
                accounts._basic_auth_login("myuser", "mypass", pyramid_request)
                is principals
            )

        assert service.find_userid.calls == [pretend.call("myuser")]
        assert service.get_user.calls == [pretend.call(2)]
        assert service.is_disabled.calls == [pretend.call(2)]
        assert service.check_password.calls == [
            pretend.call(2, "mypass", tags=["method:auth", "auth_method:basic"])
        ]
        assert breach_service.check_password.calls == [
            pretend.call("mypass", tags=["method:auth", "auth_method:basic"])
        ]
        assert service.update_user.calls == [pretend.call(2, last_login=now)]
        assert authenticate.calls == [pretend.call(2, pyramid_request)]

    def test_via_basic_auth_compromised(
        self, monkeypatch, pyramid_request, pyramid_services
    ):
        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            accounts, "send_password_compromised_email_hibp", send_email
        )

        user = pretend.stub(id=2)
        service = pretend.stub(
            get_user=pretend.call_recorder(lambda user_id: user),
            find_userid=pretend.call_recorder(lambda username: 2),
            check_password=pretend.call_recorder(
                lambda userid, password, tags=None: True
            ),
            is_disabled=pretend.call_recorder(lambda user_id: (False, None)),
            disable_password=pretend.call_recorder(lambda user_id, reason=None: None),
        )
        breach_service = pretend.stub(
            check_password=pretend.call_recorder(lambda pw, tags=None: True),
            failure_message_plain="Bad Password!",
        )

        pyramid_services.register_service(service, IUserService, None)
        pyramid_services.register_service(
            breach_service, IPasswordBreachedService, None
        )

        pyramid_request.matched_route = pretend.stub(name="forklift.legacy.file_upload")

        with pytest.raises(BasicAuthBreachedPassword) as excinfo:
            accounts._basic_auth_login("myuser", "mypass", pyramid_request)

        assert excinfo.value.status == "401 Bad Password!"
        assert service.find_userid.calls == [pretend.call("myuser")]
        assert service.get_user.calls == [pretend.call(2)]
        assert service.is_disabled.calls == [pretend.call(2)]
        assert service.check_password.calls == [
            pretend.call(2, "mypass", tags=["method:auth", "auth_method:basic"])
        ]
        assert breach_service.check_password.calls == [
            pretend.call("mypass", tags=["method:auth", "auth_method:basic"])
        ]
        assert service.disable_password.calls == [
            pretend.call(2, reason=DisableReason.CompromisedPassword)
        ]
        assert send_email.calls == [pretend.call(pyramid_request, user)]


class TestAuthenticate:
    @pytest.mark.parametrize(
        ("is_superuser", "is_moderator", "expected"),
        [
            (False, False, []),
            (True, False, ["group:admins", "group:moderators"]),
            (False, True, ["group:moderators"]),
            (True, True, ["group:admins", "group:moderators"]),
        ],
    )
    def test_with_user(self, is_superuser, is_moderator, expected):
        user = pretend.stub(is_superuser=is_superuser, is_moderator=is_moderator)
        service = pretend.stub(get_user=pretend.call_recorder(lambda userid: user))
        request = pretend.stub(find_service=lambda iface, context: service)

        assert accounts._authenticate(1, request) == expected
        assert service.get_user.calls == [pretend.call(1)]

    def test_without_user(self):
        service = pretend.stub(get_user=pretend.call_recorder(lambda userid: None))
        request = pretend.stub(find_service=lambda iface, context: service)

        assert accounts._authenticate(1, request) is None
        assert service.get_user.calls == [pretend.call(1)]


class TestSessionAuthenticate:
    def test_route_matched_name_bad(self, monkeypatch):
        authenticate_obj = pretend.call_recorder(lambda *a, **kw: True)
        monkeypatch.setattr(accounts, "_authenticate", authenticate_obj)
        request = pretend.stub(
            matched_route=pretend.stub(name="forklift.legacy.file_upload")
        )
        assert accounts._session_authenticate(1, request) is None
        assert authenticate_obj.calls == []

    def test_route_matched_name_ok(self, monkeypatch):
        authenticate_obj = pretend.call_recorder(lambda *a, **kw: True)
        monkeypatch.setattr(accounts, "_authenticate", authenticate_obj)
        request = pretend.stub(
            matched_route=pretend.stub(name="includes.current-user-indicator")
        )
        assert accounts._session_authenticate(1, request) is True
        assert authenticate_obj.calls == [pretend.call(1, request)]


class TestUser:
    def test_with_user(self):
        user = pretend.stub()
        service = pretend.stub(get_user=pretend.call_recorder(lambda userid: user))

        request = pretend.stub(
            find_service=lambda iface, context: service, authenticated_userid=100
        )

        assert accounts._user(request) is user
        assert service.get_user.calls == [pretend.call(100)]

    def test_without_users(self):
        service = pretend.stub(get_user=pretend.call_recorder(lambda userid: None))

        request = pretend.stub(
            find_service=lambda iface, context: service, authenticated_userid=100
        )

        assert accounts._user(request) is None
        assert service.get_user.calls == [pretend.call(100)]

    def test_without_userid(self):
        request = pretend.stub(authenticated_userid=None)
        assert accounts._user(request) is None


def test_includeme(monkeypatch):
    macaroon_authn_obj = pretend.stub()
    macaroon_authn_cls = pretend.call_recorder(lambda callback: macaroon_authn_obj)
    basic_authn_obj = pretend.stub()
    basic_authn_cls = pretend.call_recorder(lambda check: basic_authn_obj)
    session_authn_obj = pretend.stub()
    session_authn_cls = pretend.call_recorder(lambda callback: session_authn_obj)
    authn_obj = pretend.stub()
    authn_cls = pretend.call_recorder(lambda *a: authn_obj)
    authz_obj = pretend.stub()
    authz_cls = pretend.call_recorder(lambda *a, **kw: authz_obj)
    headers_pred_cls = pretend.stub()
    monkeypatch.setattr(accounts, "BasicAuthAuthenticationPolicy", basic_authn_cls)
    monkeypatch.setattr(accounts, "SessionAuthenticationPolicy", session_authn_cls)
    monkeypatch.setattr(accounts, "MacaroonAuthenticationPolicy", macaroon_authn_cls)
    monkeypatch.setattr(accounts, "MultiAuthenticationPolicy", authn_cls)
    monkeypatch.setattr(accounts, "ACLAuthorizationPolicy", authz_cls)
    monkeypatch.setattr(accounts, "MacaroonAuthorizationPolicy", authz_cls)
    monkeypatch.setattr(accounts, "HeadersPredicate", headers_pred_cls)

    config = pretend.stub(
        registry=pretend.stub(settings={}),
        register_service_factory=pretend.call_recorder(
            lambda factory, iface, name=None: None
        ),
        add_request_method=pretend.call_recorder(lambda f, name, reify: None),
        set_authentication_policy=pretend.call_recorder(lambda p: None),
        set_authorization_policy=pretend.call_recorder(lambda p: None),
        maybe_dotted=pretend.call_recorder(lambda path: path),
        add_route_predicate=pretend.call_recorder(lambda name, cls: None),
    )

    accounts.includeme(config)

    assert config.register_service_factory.calls == [
        pretend.call(database_login_factory, IUserService),
        pretend.call(
            TokenServiceFactory(name="password"), ITokenService, name="password"
        ),
        pretend.call(TokenServiceFactory(name="email"), ITokenService, name="email"),
        pretend.call(
            TokenServiceFactory(name="two_factor"), ITokenService, name="two_factor"
        ),
        pretend.call(
            HaveIBeenPwnedPasswordBreachedService.create_service,
            IPasswordBreachedService,
        ),
        pretend.call(
            GitHubTokenScanningPayloadVerifyService.create_service,
            IGitHubTokenScanningPayloadVerifyService,
        ),
        pretend.call(RateLimit("10 per 5 minutes"), IRateLimiter, name="user.login"),
        pretend.call(
            RateLimit("1000 per 5 minutes"), IRateLimiter, name="global.login"
        ),
        pretend.call(RateLimit("2 per day"), IRateLimiter, name="email.add"),
    ]
    assert config.add_request_method.calls == [
        pretend.call(accounts._user, name="user", reify=True)
    ]
    assert config.set_authentication_policy.calls == [pretend.call(authn_obj)]
    assert config.set_authorization_policy.calls == [pretend.call(authz_obj)]
    assert basic_authn_cls.calls == [pretend.call(check=accounts._basic_auth_login)]
    assert session_authn_cls.calls == [
        pretend.call(callback=accounts._session_authenticate)
    ]
    assert authn_cls.calls == [
        pretend.call([session_authn_obj, basic_authn_obj, macaroon_authn_obj])
    ]
    assert authz_cls.calls == [pretend.call(), pretend.call(policy=authz_obj)]
    assert config.add_route_predicate.calls == [
        pretend.call("headers", headers_pred_cls)
    ]
