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

from pyramid.interfaces import IAuthorizationPolicy, ISecurityPolicy
from pyramid.security import Allowed, Denied
from zope.interface.verify import verifyClass

from warehouse.accounts import security_policy
from warehouse.accounts.interfaces import IUserService
from warehouse.errors import WarehouseDenied
from warehouse.utils.security_policy import AuthenticationMethod

from ...common.db.packaging import ProjectFactory


class TestBasicAuthSecurityPolicy:
    def test_verify(self):
        assert verifyClass(
            ISecurityPolicy,
            security_policy.BasicAuthSecurityPolicy,
        )

    def test_noops(self):
        policy = security_policy.BasicAuthSecurityPolicy()
        assert policy.authenticated_userid(pretend.stub()) == NotImplemented
        assert (
            policy.permits(pretend.stub(), pretend.stub(), pretend.stub())
            == NotImplemented
        )

    def test_forget_and_remember(self):
        policy = security_policy.BasicAuthSecurityPolicy()

        assert policy.forget(pretend.stub()) == []
        assert policy.remember(pretend.stub(), pretend.stub()) == [
            ("WWW-Authenticate", 'Basic realm="Realm"')
        ]

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
            add_response_callback=pretend.call_recorder(lambda cb: None)
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

        basic_auth_check = pretend.call_recorder(lambda u, p, r: False)
        monkeypatch.setattr(security_policy, "_basic_auth_check", basic_auth_check)

        policy = security_policy.BasicAuthSecurityPolicy()

        vary_cb = pretend.stub()
        add_vary_cb = pretend.call_recorder(lambda *v: vary_cb)
        monkeypatch.setattr(security_policy, "add_vary_callback", add_vary_cb)

        request = pretend.stub(
            add_response_callback=pretend.call_recorder(lambda cb: None)
        )

        assert policy.identity(request) is None
        assert extract_http_basic_credentials.calls == [pretend.call(request)]
        assert basic_auth_check.calls == [pretend.call(creds[0], creds[1], request)]
        assert add_vary_cb.calls == [pretend.call("Authorization")]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]

    def test_identity(self, monkeypatch):
        creds = (pretend.stub(), pretend.stub())
        extract_http_basic_credentials = pretend.call_recorder(lambda request: creds)
        monkeypatch.setattr(
            security_policy,
            "extract_http_basic_credentials",
            extract_http_basic_credentials,
        )

        basic_auth_check = pretend.call_recorder(lambda u, p, r: True)
        monkeypatch.setattr(security_policy, "_basic_auth_check", basic_auth_check)

        policy = security_policy.BasicAuthSecurityPolicy()

        vary_cb = pretend.stub()
        add_vary_cb = pretend.call_recorder(lambda *v: vary_cb)
        monkeypatch.setattr(security_policy, "add_vary_callback", add_vary_cb)

        user = pretend.stub()
        user_service = pretend.stub(
            get_user_by_username=pretend.call_recorder(lambda u: user)
        )
        request = pretend.stub(
            add_response_callback=pretend.call_recorder(lambda cb: None),
            find_service=pretend.call_recorder(lambda a, **kw: user_service),
        )

        assert policy.identity(request) is user
        assert request.authentication_method == AuthenticationMethod.BASIC_AUTH
        assert extract_http_basic_credentials.calls == [pretend.call(request)]
        assert basic_auth_check.calls == [pretend.call(creds[0], creds[1], request)]
        assert request.find_service.calls == [pretend.call(IUserService, context=None)]
        assert user_service.get_user_by_username.calls == [pretend.call(creds[0])]

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
        assert policy.authenticated_userid(pretend.stub()) == NotImplemented
        assert (
            policy.permits(pretend.stub(), pretend.stub(), pretend.stub())
            == NotImplemented
        )

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

    def test_identity_no_session(self, monkeypatch):
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
            add_response_callback=pretend.call_recorder(lambda cb: None)
        )

        assert policy.identity(request) is None
        assert request.authentication_method == AuthenticationMethod.SESSION
        assert session_helper_obj.authenticated_userid.calls == [pretend.call(request)]
        assert session_helper_cls.calls == [pretend.call()]

        assert add_vary_cb.calls == [pretend.call("Cookie")]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]

    def test_identity_invalid_route(self, monkeypatch):
        session_helper_obj = pretend.stub(
            authenticated_userid=pretend.call_recorder(lambda r: pretend.stub())
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
            matched_route=pretend.stub(name="forklift.legacy.file_upload"),
        )

        assert policy.identity(request) is None
        assert request.authentication_method == AuthenticationMethod.SESSION
        assert session_helper_obj.authenticated_userid.calls == [pretend.call(request)]
        assert session_helper_cls.calls == [pretend.call()]

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

        timestamp = pretend.stub()
        user_service = pretend.stub(
            get_password_timestamp=pretend.call_recorder(lambda uid: timestamp),
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
        )

        assert policy.identity(request) is None
        assert request.authentication_method == AuthenticationMethod.SESSION
        assert session_helper_obj.authenticated_userid.calls == [pretend.call(request)]
        assert session_helper_cls.calls == [pretend.call()]
        assert request.find_service.calls == [pretend.call(IUserService, context=None)]
        assert request.session.password_outdated.calls == [pretend.call(timestamp)]
        assert user_service.get_password_timestamp.calls == [pretend.call(userid)]
        assert request.session.invalidate.calls == [pretend.call()]
        assert request.session.flash.calls == [
            pretend.call("Session invalidated by password change", queue="error")
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
        )
        request = pretend.stub(
            add_response_callback=pretend.call_recorder(lambda cb: None),
            matched_route=pretend.stub(name="a.permitted.route"),
            find_service=pretend.call_recorder(lambda i, **kw: user_service),
            session=pretend.stub(
                password_outdated=pretend.call_recorder(lambda ts: False)
            ),
        )

        assert policy.identity(request) is user
        assert request.authentication_method == AuthenticationMethod.SESSION
        assert session_helper_obj.authenticated_userid.calls == [pretend.call(request)]
        assert session_helper_cls.calls == [pretend.call()]
        assert request.find_service.calls == [pretend.call(IUserService, context=None)]
        assert request.session.password_outdated.calls == [pretend.call(timestamp)]
        assert user_service.get_password_timestamp.calls == [pretend.call(userid)]
        assert user_service.get_user.calls == [pretend.call(userid)]

        assert add_vary_cb.calls == [pretend.call("Cookie")]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]


class TestTwoFactorAuthorizationPolicy:
    def test_verify(self):
        assert verifyClass(
            IAuthorizationPolicy, security_policy.TwoFactorAuthorizationPolicy
        )

    def test_permits_no_active_request(self, monkeypatch):
        get_current_request = pretend.call_recorder(lambda: None)
        monkeypatch.setattr(security_policy, "get_current_request", get_current_request)

        backing_policy = pretend.stub(
            permits=pretend.call_recorder(lambda *a, **kw: pretend.stub())
        )
        policy = security_policy.TwoFactorAuthorizationPolicy(policy=backing_policy)
        result = policy.permits(pretend.stub(), pretend.stub(), pretend.stub())

        assert result == WarehouseDenied("")
        assert result.s == "There was no active request."

    def test_permits_if_context_is_not_permitted_by_backing_policy(self, monkeypatch):
        request = pretend.stub()
        get_current_request = pretend.call_recorder(lambda: request)
        monkeypatch.setattr(security_policy, "get_current_request", get_current_request)

        permits_result = Denied("Because")
        backing_policy = pretend.stub(
            permits=pretend.call_recorder(lambda *a, **kw: permits_result)
        )
        policy = security_policy.TwoFactorAuthorizationPolicy(policy=backing_policy)
        result = policy.permits(pretend.stub(), pretend.stub(), pretend.stub())

        assert result == permits_result

    def test_permits_if_non_2fa_requireable_context(self, monkeypatch):
        request = pretend.stub()
        get_current_request = pretend.call_recorder(lambda: request)
        monkeypatch.setattr(security_policy, "get_current_request", get_current_request)

        permits_result = Allowed("Because")
        backing_policy = pretend.stub(
            permits=pretend.call_recorder(lambda *a, **kw: permits_result)
        )
        policy = security_policy.TwoFactorAuthorizationPolicy(policy=backing_policy)
        result = policy.permits(pretend.stub(), pretend.stub(), pretend.stub())

        assert result == permits_result

    def test_permits_if_context_does_not_require_2fa(self, monkeypatch, db_request):
        db_request.registry.settings = {
            "warehouse.two_factor_mandate.enabled": True,
            "warehouse.two_factor_mandate.available": True,
            "warehouse.two_factor_requirement.enabled": True,
        }
        get_current_request = pretend.call_recorder(lambda: db_request)
        monkeypatch.setattr(security_policy, "get_current_request", get_current_request)

        permits_result = Allowed("Because")
        backing_policy = pretend.stub(
            permits=pretend.call_recorder(lambda *a, **kw: permits_result)
        )
        policy = security_policy.TwoFactorAuthorizationPolicy(policy=backing_policy)
        context = ProjectFactory.create(
            owners_require_2fa=False,
            pypi_mandates_2fa=False,
        )
        result = policy.permits(context, pretend.stub(), pretend.stub())

        assert result == permits_result

    def test_flashes_if_context_requires_2fa_but_not_enabled(
        self, monkeypatch, db_request
    ):
        db_request.registry.settings = {
            "warehouse.two_factor_mandate.enabled": False,
            "warehouse.two_factor_mandate.available": True,
            "warehouse.two_factor_requirement.enabled": True,
        }
        db_request.session.flash = pretend.call_recorder(lambda m, queue: None)
        db_request.user = pretend.stub(has_two_factor=False)
        get_current_request = pretend.call_recorder(lambda: db_request)
        monkeypatch.setattr(security_policy, "get_current_request", get_current_request)

        permits_result = Allowed("Because")
        backing_policy = pretend.stub(
            permits=pretend.call_recorder(lambda *a, **kw: permits_result)
        )
        policy = security_policy.TwoFactorAuthorizationPolicy(policy=backing_policy)
        context = ProjectFactory.create(
            owners_require_2fa=False,
            pypi_mandates_2fa=True,
        )
        result = policy.permits(context, pretend.stub(), pretend.stub())

        assert result == permits_result
        assert db_request.session.flash.calls == [
            pretend.call(
                "This project is included in PyPI's two-factor mandate "
                "for critical projects. In the future, you will be unable to "
                "perform this action without enabling 2FA for your account",
                queue="warning",
            ),
        ]

    @pytest.mark.parametrize("owners_require_2fa", [True, False])
    @pytest.mark.parametrize("pypi_mandates_2fa", [True, False])
    @pytest.mark.parametrize("two_factor_requirement_enabled", [True, False])
    @pytest.mark.parametrize("two_factor_mandate_available", [True, False])
    @pytest.mark.parametrize("two_factor_mandate_enabled", [True, False])
    def test_permits_if_user_has_2fa(
        self,
        monkeypatch,
        owners_require_2fa,
        pypi_mandates_2fa,
        two_factor_requirement_enabled,
        two_factor_mandate_available,
        two_factor_mandate_enabled,
        db_request,
    ):
        db_request.registry.settings = {
            "warehouse.two_factor_requirement.enabled": two_factor_requirement_enabled,
            "warehouse.two_factor_mandate.available": two_factor_mandate_available,
            "warehouse.two_factor_mandate.enabled": two_factor_mandate_enabled,
        }
        user = pretend.stub(has_two_factor=True)
        db_request.user = user
        get_current_request = pretend.call_recorder(lambda: db_request)
        monkeypatch.setattr(security_policy, "get_current_request", get_current_request)

        permits_result = Allowed("Because")
        backing_policy = pretend.stub(
            permits=pretend.call_recorder(lambda *a, **kw: permits_result)
        )
        policy = security_policy.TwoFactorAuthorizationPolicy(policy=backing_policy)
        context = ProjectFactory.create(
            owners_require_2fa=owners_require_2fa, pypi_mandates_2fa=pypi_mandates_2fa
        )
        result = policy.permits(context, pretend.stub(), pretend.stub())

        assert result == permits_result

    @pytest.mark.parametrize(
        "owners_require_2fa, pypi_mandates_2fa, reason",
        [
            (True, False, "owners_require_2fa"),
            (False, True, "pypi_mandates_2fa"),
            (True, True, "pypi_mandates_2fa"),
        ],
    )
    def test_denies_if_2fa_is_required_but_user_doesnt_have_2fa(
        self,
        monkeypatch,
        owners_require_2fa,
        pypi_mandates_2fa,
        reason,
        db_request,
    ):
        db_request.registry.settings = {
            "warehouse.two_factor_requirement.enabled": owners_require_2fa,
            "warehouse.two_factor_mandate.enabled": pypi_mandates_2fa,
        }
        user = pretend.stub(has_two_factor=False)
        db_request.user = user
        get_current_request = pretend.call_recorder(lambda: db_request)
        monkeypatch.setattr(security_policy, "get_current_request", get_current_request)

        permits_result = Allowed("Because")
        backing_policy = pretend.stub(
            permits=pretend.call_recorder(lambda *a, **kw: permits_result)
        )
        policy = security_policy.TwoFactorAuthorizationPolicy(policy=backing_policy)
        context = ProjectFactory.create(
            owners_require_2fa=owners_require_2fa, pypi_mandates_2fa=pypi_mandates_2fa
        )
        result = policy.permits(context, pretend.stub(), pretend.stub())

        summary = {
            "owners_require_2fa": (
                "This project requires two factor authentication to be enabled "
                "for all contributors.",
            ),
            "pypi_mandates_2fa": (
                "PyPI requires two factor authentication to be enabled "
                "for all contributors to this project.",
            ),
        }[reason]

        assert result == WarehouseDenied(summary, reason="two_factor_required")

    def test_principals_allowed_by_permission(self):
        principals = pretend.stub()
        backing_policy = pretend.stub(
            principals_allowed_by_permission=pretend.call_recorder(
                lambda *a: principals
            )
        )
        policy = security_policy.TwoFactorAuthorizationPolicy(policy=backing_policy)

        assert (
            policy.principals_allowed_by_permission(pretend.stub(), pretend.stub())
            is principals
        )
