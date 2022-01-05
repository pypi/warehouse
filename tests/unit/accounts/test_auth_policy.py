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

import uuid

import pretend
import pytest

from pyramid import authentication
from pyramid.interfaces import IAuthenticationPolicy, IAuthorizationPolicy
from pyramid.security import Allowed, Denied
from zope.interface.verify import verifyClass

from warehouse.accounts import auth_policy
from warehouse.accounts.interfaces import IUserService
from warehouse.errors import WarehouseDenied

from ...common.db.packaging import ProjectFactory


class TestBasicAuthAuthenticationPolicy:
    def test_verify(self):
        assert verifyClass(
            IAuthenticationPolicy, auth_policy.BasicAuthAuthenticationPolicy
        )

    def test_unauthenticated_userid_no_userid(self, monkeypatch):
        extract_http_basic_credentials = pretend.call_recorder(lambda request: None)
        monkeypatch.setattr(
            authentication,
            "extract_http_basic_credentials",
            extract_http_basic_credentials,
        )

        policy = auth_policy.BasicAuthAuthenticationPolicy(check=pretend.stub())

        vary_cb = pretend.stub()
        add_vary_cb = pretend.call_recorder(lambda *v: vary_cb)
        monkeypatch.setattr(auth_policy, "add_vary_callback", add_vary_cb)

        request = pretend.stub(
            add_response_callback=pretend.call_recorder(lambda cb: None)
        )

        assert policy.unauthenticated_userid(request) is None
        assert extract_http_basic_credentials.calls == [pretend.call(request)]
        assert add_vary_cb.calls == [pretend.call("Authorization")]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]

    def test_unauthenticated_userid_with_userid(self, monkeypatch):
        extract_http_basic_credentials = pretend.call_recorder(
            lambda request: authentication.HTTPBasicCredentials("username", "password")
        )
        monkeypatch.setattr(
            authentication,
            "extract_http_basic_credentials",
            extract_http_basic_credentials,
        )

        policy = auth_policy.BasicAuthAuthenticationPolicy(check=pretend.stub())

        vary_cb = pretend.stub()
        add_vary_cb = pretend.call_recorder(lambda *v: vary_cb)
        monkeypatch.setattr(auth_policy, "add_vary_callback", add_vary_cb)

        userid = uuid.uuid4()
        service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: userid)
        )
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda iface, context: service),
            add_response_callback=pretend.call_recorder(lambda cb: None),
        )

        assert policy.unauthenticated_userid(request) == str(userid)
        assert extract_http_basic_credentials.calls == [pretend.call(request)]
        assert request.find_service.calls == [pretend.call(IUserService, context=None)]
        assert service.find_userid.calls == [pretend.call("username")]
        assert add_vary_cb.calls == [pretend.call("Authorization")]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]


class TestSessionAuthenticationPolicy:
    def test_verify(self):
        assert verifyClass(
            IAuthenticationPolicy, auth_policy.SessionAuthenticationPolicy
        )

    def test_unauthenticated_userid(self, monkeypatch):
        policy = auth_policy.SessionAuthenticationPolicy()

        vary_cb = pretend.stub()
        add_vary_cb = pretend.call_recorder(lambda *v: vary_cb)
        monkeypatch.setattr(auth_policy, "add_vary_callback", add_vary_cb)

        userid = pretend.stub()
        request = pretend.stub(
            session={policy.helper.userid_key: userid},
            add_response_callback=pretend.call_recorder(lambda cb: None),
        )

        assert policy.unauthenticated_userid(request) is userid
        assert add_vary_cb.calls == [pretend.call("Cookie")]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]


class TestTwoFactorAuthorizationPolicy:
    def test_verify(self):
        assert verifyClass(
            IAuthorizationPolicy, auth_policy.TwoFactorAuthorizationPolicy
        )

    def test_permits_no_active_request(self, monkeypatch):
        get_current_request = pretend.call_recorder(lambda: None)
        monkeypatch.setattr(auth_policy, "get_current_request", get_current_request)

        backing_policy = pretend.stub(
            permits=pretend.call_recorder(lambda *a, **kw: pretend.stub())
        )
        policy = auth_policy.TwoFactorAuthorizationPolicy(policy=backing_policy)
        result = policy.permits(pretend.stub(), pretend.stub(), pretend.stub())

        assert result == WarehouseDenied("")
        assert result.s == "There was no active request."

    def test_permits_if_context_is_not_permitted_by_backing_policy(self, monkeypatch):
        request = pretend.stub()
        get_current_request = pretend.call_recorder(lambda: request)
        monkeypatch.setattr(auth_policy, "get_current_request", get_current_request)

        permits_result = Denied("Because")
        backing_policy = pretend.stub(
            permits=pretend.call_recorder(lambda *a, **kw: permits_result)
        )
        policy = auth_policy.TwoFactorAuthorizationPolicy(policy=backing_policy)
        result = policy.permits(pretend.stub(), pretend.stub(), pretend.stub())

        assert result == permits_result

    def test_permits_if_non_2fa_requireable_context(self, monkeypatch):
        request = pretend.stub()
        get_current_request = pretend.call_recorder(lambda: request)
        monkeypatch.setattr(auth_policy, "get_current_request", get_current_request)

        permits_result = Allowed("Because")
        backing_policy = pretend.stub(
            permits=pretend.call_recorder(lambda *a, **kw: permits_result)
        )
        policy = auth_policy.TwoFactorAuthorizationPolicy(policy=backing_policy)
        result = policy.permits(pretend.stub(), pretend.stub(), pretend.stub())

        assert result == permits_result

    def test_permits_if_context_does_not_require_2fa(self, monkeypatch, db_request):
        get_current_request = pretend.call_recorder(lambda: db_request)
        monkeypatch.setattr(auth_policy, "get_current_request", get_current_request)

        permits_result = Allowed("Because")
        backing_policy = pretend.stub(
            permits=pretend.call_recorder(lambda *a, **kw: permits_result)
        )
        policy = auth_policy.TwoFactorAuthorizationPolicy(policy=backing_policy)
        context = ProjectFactory.create(
            owners_require_2fa=False, pypi_mandates_2fa=False
        )
        result = policy.permits(context, pretend.stub(), pretend.stub())

        assert result == permits_result

    @pytest.mark.parametrize(
        "owners_require_2fa, pypi_mandates_2fa",
        [
            (True, False),
            (False, True),
            (True, True),
        ],
    )
    def test_permits_if_user_has_2fa(
        self, monkeypatch, owners_require_2fa, pypi_mandates_2fa, db_request
    ):
        user = pretend.stub(has_two_factor=True)
        db_request.user = user
        get_current_request = pretend.call_recorder(lambda: db_request)
        monkeypatch.setattr(auth_policy, "get_current_request", get_current_request)

        permits_result = Allowed("Because")
        backing_policy = pretend.stub(
            permits=pretend.call_recorder(lambda *a, **kw: permits_result)
        )
        policy = auth_policy.TwoFactorAuthorizationPolicy(policy=backing_policy)
        context = ProjectFactory.create(
            owners_require_2fa=owners_require_2fa, pypi_mandates_2fa=pypi_mandates_2fa
        )
        result = policy.permits(context, pretend.stub(), pretend.stub())

        assert result == permits_result

    @pytest.mark.parametrize(
        "owners_require_2fa, pypi_mandates_2fa",
        [
            (True, False),
            (False, True),
            (True, True),
        ],
    )
    def test_denies_if_2fa_is_required_but_user_doesnt_have_2fa(
        self, monkeypatch, owners_require_2fa, pypi_mandates_2fa, db_request
    ):
        user = pretend.stub(has_two_factor=False)
        db_request.user = user
        get_current_request = pretend.call_recorder(lambda: db_request)
        monkeypatch.setattr(auth_policy, "get_current_request", get_current_request)

        permits_result = Allowed("Because")
        backing_policy = pretend.stub(
            permits=pretend.call_recorder(lambda *a, **kw: permits_result)
        )
        policy = auth_policy.TwoFactorAuthorizationPolicy(policy=backing_policy)
        context = ProjectFactory.create(
            owners_require_2fa=owners_require_2fa, pypi_mandates_2fa=pypi_mandates_2fa
        )
        result = policy.permits(context, pretend.stub(), pretend.stub())

        assert result == WarehouseDenied(
            "This project requires two factor authentication to be enabled "
            "for all contributors.",
            reason="two_factor_required",
        )

    def test_principals_allowed_by_permission(self):
        principals = pretend.stub()
        backing_policy = pretend.stub(
            principals_allowed_by_permission=pretend.call_recorder(
                lambda *a: principals
            )
        )
        policy = auth_policy.TwoFactorAuthorizationPolicy(policy=backing_policy)

        assert (
            policy.principals_allowed_by_permission(pretend.stub(), pretend.stub())
            is principals
        )
