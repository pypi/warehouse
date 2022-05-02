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

from pyramid.httpexceptions import HTTPUnauthorized

from warehouse import accounts
from warehouse.accounts import security_policy
from warehouse.accounts.interfaces import (
    IPasswordBreachedService,
    ITokenService,
    IUserService,
)
from warehouse.accounts.models import DisableReason
from warehouse.accounts.security_policy import _basic_auth_check
from warehouse.accounts.services import (
    HaveIBeenPwnedPasswordBreachedService,
    TokenServiceFactory,
    database_login_factory,
)
from warehouse.errors import BasicAuthBreachedPassword, BasicAuthFailedPassword
from warehouse.rate_limiting import IRateLimiter, RateLimit


class TestLogin:
    def test_invalid_route(self, pyramid_request, pyramid_services):
        service = pretend.stub(find_userid=pretend.call_recorder(lambda username: None))
        pyramid_services.register_service(service, IUserService, None)
        pyramid_services.register_service(
            pretend.stub(), IPasswordBreachedService, None
        )
        pyramid_request.matched_route = pretend.stub(name="route_name")
        assert _basic_auth_check("myuser", "mypass", pyramid_request) is False
        assert service.find_userid.calls == []

    def test_with_no_user(self, pyramid_request, pyramid_services):
        service = pretend.stub(find_userid=pretend.call_recorder(lambda username: None))
        pyramid_services.register_service(service, IUserService, None)
        pyramid_services.register_service(
            pretend.stub(), IPasswordBreachedService, None
        )
        pyramid_request.matched_route = pretend.stub(name="forklift.legacy.file_upload")
        assert _basic_auth_check("myuser", "mypass", pyramid_request) is False
        assert service.find_userid.calls == [pretend.call("myuser")]

    def test_with_invalid_password(self, pyramid_request, pyramid_services):
        user = pretend.stub(
            id=1,
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
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
        pyramid_request.help_url = pretend.call_recorder(lambda **kw: "/the/help/url/")

        with pytest.raises(BasicAuthFailedPassword) as excinfo:
            assert _basic_auth_check("myuser", "mypass", pyramid_request) is None

        assert excinfo.value.status == (
            "403 Invalid or non-existent authentication information. "
            "See /the/help/url/ for more information."
        )
        assert service.find_userid.calls == [pretend.call("myuser")]
        assert service.get_user.calls == [pretend.call(1)]
        assert service.is_disabled.calls == [pretend.call(1)]
        assert service.check_password.calls == [
            pretend.call(
                1,
                "mypass",
                tags=["mechanism:basic_auth", "method:auth", "auth_method:basic"],
            )
        ]
        assert user.record_event.calls == [
            pretend.call(
                tag="account:login:failure",
                ip_address="1.2.3.4",
                additional={"reason": "invalid_password", "auth_method": "basic"},
            )
        ]

    def test_with_disabled_user_no_reason(self, pyramid_request, pyramid_services):
        user = pretend.stub(
            id=1,
            record_event=pretend.call_recorder(lambda *a, **kw: None),
        )
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
        pyramid_request.help_url = pretend.call_recorder(lambda **kw: "/the/help/url/")

        with pytest.raises(HTTPUnauthorized) as excinfo:
            assert _basic_auth_check("myuser", "mypass", pyramid_request) is None

        assert excinfo.value.status == "401 Account is disabled."
        assert service.find_userid.calls == [pretend.call("myuser")]
        assert service.get_user.calls == [pretend.call(1)]
        assert service.is_disabled.calls == [pretend.call(1)]

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
            assert _basic_auth_check("myuser", "mypass", pyramid_request) is None

        assert excinfo.value.status == "401 Bad Password!"
        assert service.find_userid.calls == [pretend.call("myuser")]
        assert service.get_user.calls == [pretend.call(1)]
        assert service.is_disabled.calls == [pretend.call(1)]
        assert service.check_password.calls == []

    def test_with_disabled_user_frozen(self, pyramid_request, pyramid_services):
        user = pretend.stub(
            id=1,
            record_event=pretend.call_recorder(lambda *a, **kw: None),
            is_frozen=True,
        )
        service = pretend.stub(
            get_user=pretend.call_recorder(lambda user_id: user),
            find_userid=pretend.call_recorder(lambda username: 1),
            check_password=pretend.call_recorder(
                lambda userid, password, tags=None: False
            ),
            is_disabled=pretend.call_recorder(
                lambda user_id: (True, DisableReason.AccountFrozen)
            ),
        )
        pyramid_services.register_service(service, IUserService, None)
        pyramid_services.register_service(
            pretend.stub(), IPasswordBreachedService, None
        )
        pyramid_request.matched_route = pretend.stub(name="forklift.legacy.file_upload")
        pyramid_request.help_url = pretend.call_recorder(lambda **kw: "/the/help/url/")

        with pytest.raises(HTTPUnauthorized) as excinfo:
            assert _basic_auth_check("myuser", "mypass", pyramid_request) is None

        assert excinfo.value.status == "401 Account is frozen."
        assert service.find_userid.calls == [pretend.call("myuser")]
        assert service.get_user.calls == [pretend.call(1)]
        assert service.is_disabled.calls == [pretend.call(1)]

    def test_with_valid_password(self, monkeypatch, pyramid_request, pyramid_services):
        user = pretend.stub(id=2, has_two_factor=False)
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
            assert _basic_auth_check("myuser", "mypass", pyramid_request) is True

        assert service.find_userid.calls == [pretend.call("myuser")]
        assert service.get_user.calls == [pretend.call(2)]
        assert service.is_disabled.calls == [pretend.call(2)]
        assert service.check_password.calls == [
            pretend.call(
                2,
                "mypass",
                tags=["mechanism:basic_auth", "method:auth", "auth_method:basic"],
            )
        ]
        assert breach_service.check_password.calls == [
            pretend.call("mypass", tags=["method:auth", "auth_method:basic"])
        ]
        assert service.update_user.calls == [pretend.call(2, last_login=now)]

    def test_via_basic_auth_compromised(
        self, monkeypatch, pyramid_request, pyramid_services
    ):
        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            security_policy, "send_password_compromised_email_hibp", send_email
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
            _basic_auth_check("myuser", "mypass", pyramid_request)

        assert excinfo.value.status == "401 Bad Password!"
        assert service.find_userid.calls == [pretend.call("myuser")]
        assert service.get_user.calls == [pretend.call(2)]
        assert service.is_disabled.calls == [pretend.call(2)]
        assert service.check_password.calls == [
            pretend.call(
                2,
                "mypass",
                tags=["mechanism:basic_auth", "method:auth", "auth_method:basic"],
            )
        ]
        assert breach_service.check_password.calls == [
            pretend.call("mypass", tags=["method:auth", "auth_method:basic"])
        ]
        assert service.disable_password.calls == [
            pretend.call(2, reason=DisableReason.CompromisedPassword)
        ]
        assert send_email.calls == [pretend.call(pyramid_request, user)]


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
    authz_obj = pretend.stub()
    authz_cls = pretend.call_recorder(lambda *a, **kw: authz_obj)
    monkeypatch.setattr(accounts, "ACLAuthorizationPolicy", authz_cls)
    monkeypatch.setattr(accounts, "MacaroonAuthorizationPolicy", authz_cls)
    monkeypatch.setattr(accounts, "TwoFactorAuthorizationPolicy", authz_cls)

    multi_policy_obj = pretend.stub()
    multi_policy_cls = pretend.call_recorder(lambda ps, authz: multi_policy_obj)
    monkeypatch.setattr(accounts, "MultiSecurityPolicy", multi_policy_cls)

    session_policy_obj = pretend.stub()
    session_policy_cls = pretend.call_recorder(lambda: session_policy_obj)
    monkeypatch.setattr(accounts, "SessionSecurityPolicy", session_policy_cls)

    basic_policy_obj = pretend.stub()
    basic_policy_cls = pretend.call_recorder(lambda: basic_policy_obj)
    monkeypatch.setattr(accounts, "BasicAuthSecurityPolicy", basic_policy_cls)

    macaroon_policy_obj = pretend.stub()
    macaroon_policy_cls = pretend.call_recorder(lambda: macaroon_policy_obj)
    monkeypatch.setattr(accounts, "MacaroonSecurityPolicy", macaroon_policy_cls)

    config = pretend.stub(
        registry=pretend.stub(
            settings={
                "warehouse.account.user_login_ratelimit_string": "10 per 5 minutes",
                "warehouse.account.ip_login_ratelimit_string": "10 per 5 minutes",
                "warehouse.account.global_login_ratelimit_string": "1000 per 5 minutes",
                "warehouse.account.email_add_ratelimit_string": "2 per day",
                "warehouse.account.password_reset_ratelimit_string": "5 per day",
            }
        ),
        register_service_factory=pretend.call_recorder(
            lambda factory, iface, name=None: None
        ),
        add_request_method=pretend.call_recorder(lambda f, name, reify: None),
        set_security_policy=pretend.call_recorder(lambda p: None),
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
        pretend.call(RateLimit("10 per 5 minutes"), IRateLimiter, name="user.login"),
        pretend.call(RateLimit("10 per 5 minutes"), IRateLimiter, name="ip.login"),
        pretend.call(
            RateLimit("1000 per 5 minutes"), IRateLimiter, name="global.login"
        ),
        pretend.call(RateLimit("2 per day"), IRateLimiter, name="email.add"),
        pretend.call(RateLimit("5 per day"), IRateLimiter, name="password.reset"),
    ]
    assert config.add_request_method.calls == [
        pretend.call(accounts._user, name="user", reify=True)
    ]
    assert config.set_security_policy.calls == [pretend.call(multi_policy_obj)]
    assert multi_policy_cls.calls == [
        pretend.call(
            [session_policy_obj, basic_policy_obj, macaroon_policy_obj], authz_obj
        )
    ]
