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

from pyramid.authorization import Allow
from pyramid.exceptions import HTTPForbidden
from pyramid.interfaces import ISecurityPolicy
from zope.interface.verify import verifyClass

from warehouse.accounts import UserContext, security_policy
from warehouse.accounts.interfaces import IUserService
from warehouse.utils.security_policy import AuthenticationMethod


class TestBasicAuthSecurityPolicy:
    def test_verify(self):
        assert verifyClass(
            ISecurityPolicy,
            security_policy.BasicAuthSecurityPolicy,
        )

    def test_noops(self):
        """Basically, anything that isn't `identity()` is a no-op."""
        policy = security_policy.BasicAuthSecurityPolicy()
        with pytest.raises(NotImplementedError):
            policy.authenticated_userid(pretend.stub())
        with pytest.raises(NotImplementedError):
            policy.permits(pretend.stub(), pretend.stub(), pretend.stub())

        # These are no-ops, but they don't raise, used in MultiSecurityPolicy
        assert policy.forget(pretend.stub()) == []
        assert policy.remember(pretend.stub(), pretend.stub()) == []

    def test_identity_no_credentials(self, monkeypatch):
        extract_http_basic_credentials = pretend.call_recorder(lambda request: None)
        monkeypatch.setattr(
            security_policy,
            "extract_http_basic_credentials",
            extract_http_basic_credentials,
        )

        policy = security_policy.BasicAuthSecurityPolicy()

        vary_cb = pretend.stub()
        add_vary_cb = pretend.call_recorder(lambda *v: vary_cb)
        monkeypatch.setattr(security_policy, "add_vary_callback", add_vary_cb)

        request = pretend.stub(
            add_response_callback=pretend.call_recorder(lambda cb: None),
            matched_route=pretend.stub(name="forklift.legacy.file_upload"),
        )

        assert policy.identity(request) is None
        assert extract_http_basic_credentials.calls == [pretend.call(request)]
        assert add_vary_cb.calls == [pretend.call("Authorization")]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]

    def test_identity_credentials_fail(self, monkeypatch):
        creds = (pretend.stub(), pretend.stub())
        extract_http_basic_credentials = pretend.call_recorder(lambda request: creds)
        monkeypatch.setattr(
            security_policy,
            "extract_http_basic_credentials",
            extract_http_basic_credentials,
        )

        policy = security_policy.BasicAuthSecurityPolicy()

        vary_cb = pretend.stub()
        add_vary_cb = pretend.call_recorder(lambda *v: vary_cb)
        monkeypatch.setattr(security_policy, "add_vary_callback", add_vary_cb)

        request = pretend.stub(
            add_response_callback=pretend.call_recorder(lambda cb: None),
            help_url=lambda _anchor=None: "/help",
            matched_route=pretend.stub(name="forklift.legacy.file_upload"),
        )

        with pytest.raises(HTTPForbidden):
            policy.identity(request)
        assert extract_http_basic_credentials.calls == [pretend.call(request)]
        assert add_vary_cb.calls == [pretend.call("Authorization")]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]

    @pytest.mark.parametrize(
        "fake_request",
        [
            pretend.stub(
                matched_route=None,
                banned=pretend.stub(by_ip=lambda ip_address: False),
                remote_addr="1.2.3.4",
            ),
            pretend.stub(
                matched_route=pretend.stub(name="an.invalid.route"),
                banned=pretend.stub(by_ip=lambda ip_address: False),
                remote_addr="1.2.3.4",
            ),
        ],
    )
    def test_invalid_request_fail(self, monkeypatch, fake_request):
        creds = (pretend.stub(), pretend.stub())
        extract_http_basic_credentials = pretend.call_recorder(lambda request: creds)
        monkeypatch.setattr(
            security_policy,
            "extract_http_basic_credentials",
            extract_http_basic_credentials,
        )
        policy = security_policy.BasicAuthSecurityPolicy()
        fake_request.add_response_callback = pretend.call_recorder(lambda cb: None)

        assert policy.identity(fake_request) is None

    def test_identity(self, monkeypatch):
        creds = ("__token__", pretend.stub())
        extract_http_basic_credentials = pretend.call_recorder(lambda request: creds)
        monkeypatch.setattr(
            security_policy,
            "extract_http_basic_credentials",
            extract_http_basic_credentials,
        )

        policy = security_policy.BasicAuthSecurityPolicy()

        vary_cb = pretend.stub()
        add_vary_cb = pretend.call_recorder(lambda *v: vary_cb)
        monkeypatch.setattr(security_policy, "add_vary_callback", add_vary_cb)

        request = pretend.stub(
            add_response_callback=pretend.call_recorder(lambda cb: None),
            help_url=lambda _anchor=None: "/help",
            matched_route=pretend.stub(name="forklift.legacy.file_upload"),
        )

        assert policy.identity(request) is None
        assert request.authentication_method == AuthenticationMethod.BASIC_AUTH
        assert extract_http_basic_credentials.calls == [pretend.call(request)]
        assert add_vary_cb.calls == [pretend.call("Authorization")]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]


class TestSessionSecurityPolicy:
    def test_verify(self):
        assert verifyClass(
            ISecurityPolicy,
            security_policy.SessionSecurityPolicy,
        )

    def test_noops(self):
        policy = security_policy.SessionSecurityPolicy()
        with pytest.raises(NotImplementedError):
            policy.authenticated_userid(pretend.stub())

    def test_forget_and_remember(self, monkeypatch):
        request = pretend.stub()
        userid = pretend.stub()
        forgets = pretend.stub()
        remembers = pretend.stub()
        session_helper_obj = pretend.stub(
            forget=pretend.call_recorder(lambda r, **kw: forgets),
            remember=pretend.call_recorder(lambda r, uid, **kw: remembers),
        )
        session_helper_cls = pretend.call_recorder(lambda: session_helper_obj)
        monkeypatch.setattr(
            security_policy, "SessionAuthenticationHelper", session_helper_cls
        )

        policy = security_policy.SessionSecurityPolicy()
        assert session_helper_cls.calls == [pretend.call()]

        assert policy.forget(request, foo=None) == forgets
        assert session_helper_obj.forget.calls == [pretend.call(request, foo=None)]

        assert policy.remember(request, userid, foo=None) == remembers
        assert session_helper_obj.remember.calls == [
            pretend.call(request, userid, foo=None)
        ]

    def test_identity_missing_route(self, monkeypatch):
        session_helper_obj = pretend.stub()
        session_helper_cls = pretend.call_recorder(lambda: session_helper_obj)
        monkeypatch.setattr(
            security_policy, "SessionAuthenticationHelper", session_helper_cls
        )

        policy = security_policy.SessionSecurityPolicy()

        vary_cb = pretend.stub()
        add_vary_cb = pretend.call_recorder(lambda *v: vary_cb)
        monkeypatch.setattr(security_policy, "add_vary_callback", add_vary_cb)

        request = pretend.stub(
            add_response_callback=pretend.call_recorder(lambda cb: None),
            matched_route=None,
            banned=pretend.stub(by_ip=lambda ip_address: False),
            remote_addr="1.2.3.4",
        )

        assert policy.identity(request) is None
        assert request.authentication_method == AuthenticationMethod.SESSION
        assert session_helper_cls.calls == [pretend.call()]

        assert add_vary_cb.calls == [pretend.call("Cookie")]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]

    @pytest.mark.parametrize(
        "route_name",
        [
            "forklift.legacy.file_upload",
            "api.echo",
        ],
    )
    def test_identity_invalid_route(self, route_name, monkeypatch):
        session_helper_obj = pretend.stub()
        session_helper_cls = pretend.call_recorder(lambda: session_helper_obj)
        monkeypatch.setattr(
            security_policy, "SessionAuthenticationHelper", session_helper_cls
        )

        policy = security_policy.SessionSecurityPolicy()

        vary_cb = pretend.stub()
        add_vary_cb = pretend.call_recorder(lambda *v: vary_cb)
        monkeypatch.setattr(security_policy, "add_vary_callback", add_vary_cb)

        request = pretend.stub(
            add_response_callback=pretend.call_recorder(lambda cb: None),
            matched_route=pretend.stub(name=route_name),
            banned=pretend.stub(by_ip=lambda ip_address: False),
            remote_addr="1.2.3.4",
        )

        assert policy.identity(request) is None
        assert request.authentication_method == AuthenticationMethod.SESSION
        assert session_helper_cls.calls == [pretend.call()]

        assert add_vary_cb.calls == [pretend.call("Cookie")]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]

    def test_identity_no_userid(self, monkeypatch):
        session_helper_obj = pretend.stub(
            authenticated_userid=pretend.call_recorder(lambda r: None)
        )
        session_helper_cls = pretend.call_recorder(lambda: session_helper_obj)
        monkeypatch.setattr(
            security_policy, "SessionAuthenticationHelper", session_helper_cls
        )

        policy = security_policy.SessionSecurityPolicy()

        vary_cb = pretend.stub()
        add_vary_cb = pretend.call_recorder(lambda *v: vary_cb)
        monkeypatch.setattr(security_policy, "add_vary_callback", add_vary_cb)

        request = pretend.stub(
            add_response_callback=pretend.call_recorder(lambda cb: None),
            matched_route=pretend.stub(name="a.permitted.route"),
            banned=pretend.stub(by_ip=lambda ip_address: False),
            remote_addr="1.2.3.4",
        )

        assert policy.identity(request) is None
        assert request.authentication_method == AuthenticationMethod.SESSION
        assert session_helper_obj.authenticated_userid.calls == [pretend.call(request)]
        assert session_helper_cls.calls == [pretend.call()]

        assert add_vary_cb.calls == [pretend.call("Cookie")]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]

    def test_identity_no_user(self, monkeypatch):
        userid = pretend.stub()
        session_helper_obj = pretend.stub(
            authenticated_userid=pretend.call_recorder(lambda r: userid)
        )
        session_helper_cls = pretend.call_recorder(lambda: session_helper_obj)
        monkeypatch.setattr(
            security_policy, "SessionAuthenticationHelper", session_helper_cls
        )

        policy = security_policy.SessionSecurityPolicy()

        vary_cb = pretend.stub()
        add_vary_cb = pretend.call_recorder(lambda *v: vary_cb)
        monkeypatch.setattr(security_policy, "add_vary_callback", add_vary_cb)

        user_service = pretend.stub(get_user=pretend.call_recorder(lambda uid: None))
        request = pretend.stub(
            add_response_callback=pretend.call_recorder(lambda cb: None),
            matched_route=pretend.stub(name="a.permitted.route"),
            find_service=pretend.call_recorder(lambda i, **kw: user_service),
            banned=pretend.stub(by_ip=lambda ip_address: False),
            remote_addr="1.2.3.4",
        )

        assert policy.identity(request) is None
        assert request.authentication_method == AuthenticationMethod.SESSION
        assert session_helper_obj.authenticated_userid.calls == [pretend.call(request)]
        assert session_helper_cls.calls == [pretend.call()]
        assert request.find_service.calls == [pretend.call(IUserService, context=None)]
        assert user_service.get_user.calls == [pretend.call(userid)]

        assert add_vary_cb.calls == [pretend.call("Cookie")]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]

    def test_identity_password_outdated(self, monkeypatch):
        userid = pretend.stub()
        session_helper_obj = pretend.stub(
            authenticated_userid=pretend.call_recorder(lambda r: userid)
        )
        session_helper_cls = pretend.call_recorder(lambda: session_helper_obj)
        monkeypatch.setattr(
            security_policy, "SessionAuthenticationHelper", session_helper_cls
        )

        policy = security_policy.SessionSecurityPolicy()

        vary_cb = pretend.stub()
        add_vary_cb = pretend.call_recorder(lambda *v: vary_cb)
        monkeypatch.setattr(security_policy, "add_vary_callback", add_vary_cb)

        user = pretend.stub()
        timestamp = pretend.stub()
        user_service = pretend.stub(
            get_user=pretend.call_recorder(lambda uid: user),
            get_password_timestamp=pretend.call_recorder(lambda uid: timestamp),
            is_disabled=lambda uid: (False, None),
        )
        request = pretend.stub(
            add_response_callback=pretend.call_recorder(lambda cb: None),
            matched_route=pretend.stub(name="a.permitted.route"),
            find_service=pretend.call_recorder(lambda i, **kw: user_service),
            session=pretend.stub(
                password_outdated=pretend.call_recorder(lambda ts: True),
                invalidate=pretend.call_recorder(lambda: None),
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
            banned=pretend.stub(by_ip=lambda ip_address: False),
            remote_addr="1.2.3.4",
        )

        assert policy.identity(request) is None
        assert request.authentication_method == AuthenticationMethod.SESSION
        assert session_helper_obj.authenticated_userid.calls == [pretend.call(request)]
        assert session_helper_cls.calls == [pretend.call()]
        assert request.find_service.calls == [pretend.call(IUserService, context=None)]
        assert user_service.get_user.calls == [pretend.call(userid)]
        assert request.session.password_outdated.calls == [pretend.call(timestamp)]
        assert user_service.get_password_timestamp.calls == [pretend.call(userid)]
        assert request.session.invalidate.calls == [pretend.call()]
        assert request.session.flash.calls == [
            pretend.call("Session invalidated by password change", queue="error")
        ]

        assert add_vary_cb.calls == [pretend.call("Cookie")]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]

    def test_identity_is_disabled(self, monkeypatch):
        userid = pretend.stub()
        session_helper_obj = pretend.stub(
            authenticated_userid=pretend.call_recorder(lambda r: userid)
        )
        session_helper_cls = pretend.call_recorder(lambda: session_helper_obj)
        monkeypatch.setattr(
            security_policy, "SessionAuthenticationHelper", session_helper_cls
        )

        policy = security_policy.SessionSecurityPolicy()

        vary_cb = pretend.stub()
        add_vary_cb = pretend.call_recorder(lambda *v: vary_cb)
        monkeypatch.setattr(security_policy, "add_vary_callback", add_vary_cb)

        user = pretend.stub()
        timestamp = pretend.stub()
        user_service = pretend.stub(
            get_user=pretend.call_recorder(lambda uid: user),
            get_password_timestamp=pretend.call_recorder(lambda uid: timestamp),
            is_disabled=pretend.call_recorder(lambda uid: (True, "Said So!")),
        )
        request = pretend.stub(
            add_response_callback=pretend.call_recorder(lambda cb: None),
            matched_route=pretend.stub(name="a.permitted.route"),
            find_service=pretend.call_recorder(lambda i, **kw: user_service),
            session=pretend.stub(
                password_outdated=pretend.call_recorder(lambda ts: True),
                invalidate=pretend.call_recorder(lambda: None),
                flash=pretend.call_recorder(lambda *a, **kw: None),
            ),
            banned=pretend.stub(by_ip=lambda ip_address: False),
            remote_addr="1.2.3.4",
        )

        assert policy.identity(request) is None
        assert request.authentication_method == AuthenticationMethod.SESSION
        assert session_helper_obj.authenticated_userid.calls == [pretend.call(request)]
        assert session_helper_cls.calls == [pretend.call()]
        assert request.find_service.calls == [pretend.call(IUserService, context=None)]
        assert user_service.get_user.calls == [pretend.call(userid)]
        assert request.session.password_outdated.calls == []
        assert user_service.get_password_timestamp.calls == []
        assert user_service.is_disabled.calls == [pretend.call(userid)]
        assert request.session.invalidate.calls == [pretend.call()]
        assert request.session.flash.calls == [
            pretend.call("Session invalidated", queue="error")
        ]

        assert add_vary_cb.calls == [pretend.call("Cookie")]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]

    def test_identity(self, monkeypatch):
        userid = pretend.stub()
        session_helper_obj = pretend.stub(
            authenticated_userid=pretend.call_recorder(lambda r: userid)
        )
        session_helper_cls = pretend.call_recorder(lambda: session_helper_obj)
        monkeypatch.setattr(
            security_policy, "SessionAuthenticationHelper", session_helper_cls
        )

        policy = security_policy.SessionSecurityPolicy()

        vary_cb = pretend.stub()
        add_vary_cb = pretend.call_recorder(lambda *v: vary_cb)
        monkeypatch.setattr(security_policy, "add_vary_callback", add_vary_cb)

        user = pretend.stub()
        timestamp = pretend.stub()
        user_service = pretend.stub(
            get_user=pretend.call_recorder(lambda uid: user),
            get_password_timestamp=pretend.call_recorder(lambda uid: timestamp),
            is_disabled=lambda uid: (False, None),
        )
        request = pretend.stub(
            add_response_callback=pretend.call_recorder(lambda cb: None),
            matched_route=pretend.stub(name="a.permitted.route"),
            find_service=pretend.call_recorder(lambda i, **kw: user_service),
            session=pretend.stub(
                password_outdated=pretend.call_recorder(lambda ts: False)
            ),
            banned=pretend.stub(by_ip=lambda ip_address: False),
            remote_addr="1.2.3.4",
        )

        assert policy.identity(request).user is user
        assert request.authentication_method == AuthenticationMethod.SESSION
        assert session_helper_obj.authenticated_userid.calls == [pretend.call(request)]
        assert session_helper_cls.calls == [pretend.call()]
        assert request.find_service.calls == [pretend.call(IUserService, context=None)]
        assert request.session.password_outdated.calls == [pretend.call(timestamp)]
        assert user_service.get_password_timestamp.calls == [pretend.call(userid)]
        assert user_service.get_user.calls == [pretend.call(userid)]

        assert add_vary_cb.calls == [pretend.call("Cookie")]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]

    def test_identity_ip_banned(self, monkeypatch):
        userid = pretend.stub()
        session_helper_obj = pretend.stub(
            authenticated_userid=pretend.call_recorder(lambda r: userid)
        )
        session_helper_cls = pretend.call_recorder(lambda: session_helper_obj)
        monkeypatch.setattr(
            security_policy, "SessionAuthenticationHelper", session_helper_cls
        )

        policy = security_policy.SessionSecurityPolicy()

        vary_cb = pretend.stub()
        add_vary_cb = pretend.call_recorder(lambda *v: vary_cb)
        monkeypatch.setattr(security_policy, "add_vary_callback", add_vary_cb)

        user = pretend.stub()
        timestamp = pretend.stub()
        user_service = pretend.stub(
            get_user=pretend.call_recorder(lambda uid: user),
            get_password_timestamp=pretend.call_recorder(lambda uid: timestamp),
        )
        request = pretend.stub(
            add_response_callback=pretend.call_recorder(lambda cb: None),
            matched_route=pretend.stub(name="a.permitted.route"),
            find_service=pretend.call_recorder(lambda i, **kw: user_service),
            session=pretend.stub(
                password_outdated=pretend.call_recorder(lambda ts: False)
            ),
            banned=pretend.stub(by_ip=lambda ip_address: True),
            remote_addr="1.2.3.4",
        )

        assert policy.identity(request) is None
        assert request.authentication_method == AuthenticationMethod.SESSION
        assert session_helper_obj.authenticated_userid.calls == []
        assert session_helper_cls.calls == [pretend.call()]
        assert request.find_service.calls == []
        assert request.session.password_outdated.calls == []
        assert user_service.get_password_timestamp.calls == []
        assert user_service.get_user.calls == []

        assert add_vary_cb.calls == [pretend.call("Cookie")]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]


@pytest.mark.parametrize(
    "policy_class",
    [security_policy.SessionSecurityPolicy],
)
class TestPermits:
    @pytest.mark.parametrize(
        "principals,expected", [("user:5", True), ("user:1", False)]
    )
    def test_acl(self, monkeypatch, policy_class, principals, expected):
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda flag: False),
            identity=UserContext(
                user=pretend.stub(
                    __principals__=lambda: principals,
                    has_primary_verified_email=True,
                    has_two_factor=True,
                ),
                macaroon=None,
            ),
            matched_route=pretend.stub(name="random.route"),
        )
        context = pretend.stub(__acl__=[(Allow, "user:5", "myperm")])

        policy = policy_class()
        assert bool(policy.permits(request, context, "myperm")) == expected

    def test_permits_with_unverified_email(self, monkeypatch, policy_class):
        request = pretend.stub(
            identity=UserContext(
                user=pretend.stub(
                    __principals__=lambda: ["user:5"],
                    has_primary_verified_email=False,
                    has_two_factor=False,
                ),
                macaroon=None,
            ),
            matched_route=pretend.stub(name="manage.projects"),
        )
        context = pretend.stub(__acl__=[(Allow, "user:5", "myperm")])

        policy = policy_class()
        assert not policy.permits(request, context, "myperm")

    def test_permits_manage_projects_with_2fa(self, monkeypatch, policy_class):
        request = pretend.stub(
            identity=UserContext(
                user=pretend.stub(
                    __principals__=lambda: ["user:5"],
                    has_primary_verified_email=True,
                    has_two_factor=True,
                ),
                macaroon=None,
            ),
            matched_route=pretend.stub(name="manage.projects"),
        )
        context = pretend.stub(__acl__=[(Allow, "user:5", "myperm")])

        policy = policy_class()
        assert policy.permits(request, context, "myperm")

    def test_deny_manage_projects_without_2fa(self, monkeypatch, policy_class):
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda flag: False),
            identity=UserContext(
                user=pretend.stub(
                    __principals__=lambda: ["user:5"],
                    has_primary_verified_email=True,
                    has_two_factor=False,
                ),
                macaroon=None,
            ),
            matched_route=pretend.stub(name="manage.projects"),
        )
        context = pretend.stub(__acl__=[(Allow, "user:5", "myperm")])

        policy = policy_class()
        assert not policy.permits(request, context, "myperm")

    def test_deny_forklift_file_upload_without_2fa(self, monkeypatch, policy_class):
        request = pretend.stub(
            flags=pretend.stub(enabled=lambda flag: False),
            identity=UserContext(
                user=pretend.stub(
                    __principals__=lambda: ["user:5"],
                    has_primary_verified_email=True,
                    has_two_factor=False,
                ),
                macaroon=None,
            ),
            matched_route=pretend.stub(name="forklift.legacy.file_upload"),
        )
        context = pretend.stub(__acl__=[(Allow, "user:5", "myperm")])

        policy = policy_class()
        assert not policy.permits(request, context, "myperm")

    @pytest.mark.parametrize(
        "matched_route",
        [
            "manage.account",
            "manage.account.recovery-codes",
            "manage.account.totp-provision",
            "manage.account.two-factor",
            "manage.account.webauthn-provision",
            "manage.account.webauthn-provision.validate",
        ],
    )
    def test_permits_2fa_routes_without_2fa(
        self, monkeypatch, policy_class, matched_route
    ):
        request = pretend.stub(
            identity=UserContext(
                user=pretend.stub(
                    __principals__=lambda: ["user:5"],
                    has_primary_verified_email=True,
                    has_two_factor=False,
                ),
                macaroon=None,
            ),
            matched_route=pretend.stub(name=matched_route),
        )

        context = pretend.stub(__acl__=[(Allow, "user:5", "myperm")])

        policy = policy_class()
        assert policy.permits(request, context, "myperm")
