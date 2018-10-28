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
import uuid

from pymacaroons import Macaroon
from pyramid import authentication, security
from pyramid.interfaces import IAuthenticationPolicy, IAuthorizationPolicy
from zope.interface.verify import verifyClass

from warehouse.accounts import auth_policy
from warehouse.accounts.interfaces import IUserService, IAccountTokenService

from ...common.db.accounts import AccountTokenFactory, UserFactory


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
            session={policy.userid_key: userid},
            add_response_callback=pretend.call_recorder(lambda cb: None),
        )

        assert policy.unauthenticated_userid(request) is userid
        assert add_vary_cb.calls == [pretend.call("Cookie")]
        assert request.add_response_callback.calls == [pretend.call(vary_cb)]


class TestAccountTokenAuthenticationPolicy:
    def test_verify(self):
        assert verifyClass(
            IAuthenticationPolicy, auth_policy.AccountTokenAuthenticationPolicy
        )

    def test_routes_not_allowed(self):
        request = pretend.stub(matched_route=pretend.stub(name="not_allowed_route"))

        authn_policy = auth_policy.AccountTokenAuthenticationPolicy(
            pretend.stub(), ["allowed_route"]
        )

        assert authn_policy.unauthenticated_userid(request) is None

    def test_require_known(self):
        # Ensure we don't accept just any macaroon
        request = pretend.stub(
            find_service=lambda iface, **kw: {
                IAccountTokenService: pretend.stub(
                    get_unverified_macaroon=(lambda: (None, None))
                )
            }[iface],
            matched_route=pretend.stub(name="allowed_route"),
            add_response_callback=lambda x: None,
        )

        authn_policy = auth_policy.AccountTokenAuthenticationPolicy(
            pretend.stub(), ["allowed_route"]
        )

        assert authn_policy.unauthenticated_userid(request) is None

    def test_macaroon_verifier(self, db_request):
        user = UserFactory.create(username="test_user")

        account_token = AccountTokenFactory.create(
            secret="some_secret", username=user.username
        )

        macaroon = Macaroon(
            location="pypi.org", identifier="some_id", key="wrong_secret"
        )

        request = pretend.stub(
            find_service=lambda iface, **kw: {
                IAccountTokenService: pretend.stub(
                    get_unverified_macaroon=(lambda: (macaroon, account_token))
                )
            }[iface],
            matched_route=pretend.stub(name="allowed_route"),
            add_response_callback=lambda x: None,
        )

        authn_policy = auth_policy.AccountTokenAuthenticationPolicy(
            pretend.stub(), ["allowed_route"]
        )

        assert authn_policy.unauthenticated_userid(request) is None

    def test_account_token_auth(self, db_request):
        # Test basic happy path
        user = UserFactory.create(username="test_user")
        account_token = AccountTokenFactory.create(
            secret="some_secret", username=user.username
        )

        macaroon = Macaroon(
            location="pypi.org", identifier=str(account_token.id), key="some_secret"
        )

        request = pretend.stub(
            find_service=lambda iface, **kw: {
                IUserService: pretend.stub(
                    find_userid=(lambda x: user.id if x == "test_user" else None)
                ),
                IAccountTokenService: pretend.stub(
                    get_unverified_macaroon=(lambda: (macaroon, account_token)),
                    update_last_used=(lambda x: None),
                ),
            }[iface],
            matched_route=pretend.stub(name="allowed_route"),
            add_response_callback=lambda x: None,
            session={},
        )

        authn_policy = auth_policy.AccountTokenAuthenticationPolicy(
            pretend.stub(), ["allowed_route"]
        )

        assert authn_policy.unauthenticated_userid(request) == user.id

        # Make sure we allow first-party and third-party caveats
        macaroon.add_first_party_caveat("first party caveat")

        macaroon.add_third_party_caveat(
            location="mysite.com", key="anykey", key_id="anykeyid"
        )

        assert authn_policy.unauthenticated_userid(request) == user.id

    def test_account_token_interface(self):
        def _authenticate(a, b):
            return a, b

        policy = auth_policy.AccountTokenAuthenticationPolicy(_authenticate, ["route"])

        assert policy.remember("", "") == []
        assert policy.forget("") == []
        assert policy._auth_callback(1, 2) == (1, 2)
        assert policy._routes_allowed == ["route"]


class TestAccountTokenAuthorizationPolicy:
    def test_verify(self):
        assert verifyClass(
            IAuthorizationPolicy, auth_policy.AccountTokenAuthorizationPolicy
        )

    def test_have_request(self, monkeypatch):
        monkeypatch.setattr(auth_policy, "get_current_request", lambda: None)
        authz_policy = auth_policy.AccountTokenAuthorizationPolicy(pretend.stub())

        assert isinstance(
            authz_policy.permits(pretend.stub(), pretend.stub(), pretend.stub()),
            security.Denied,
        )

    def test_macaroon_verifier(self, db_request, monkeypatch):
        user = UserFactory.create(username="test_user")

        account_token = AccountTokenFactory.create(
            secret="some_secret", username=user.username
        )

        macaroon = Macaroon(
            location="pypi.org", identifier="some_id", key="wrong_secret"
        )

        monkeypatch.setattr(auth_policy, "get_current_request", lambda: request)
        request = pretend.stub(
            find_service=lambda iface, **kw: {
                IAccountTokenService: pretend.stub(
                    get_unverified_macaroon=(lambda: (macaroon, account_token))
                )
            }[iface]
        )

        authz_policy = auth_policy.AccountTokenAuthorizationPolicy(pretend.stub())

        assert isinstance(
            authz_policy.permits(pretend.stub(), pretend.stub(), pretend.stub()),
            security.Denied,
        )

    def test_account_token_authz(self, db_request, monkeypatch):
        user = UserFactory.create(username="test_user")

        account_token = AccountTokenFactory.create(
            secret="some_secret", username=user.username
        )

        macaroon = Macaroon(
            location="pypi.org", identifier="some_id", key="some_secret"
        )

        monkeypatch.setattr(auth_policy, "get_current_request", lambda: request)
        request = pretend.stub(
            find_service=lambda iface, **kw: {
                IAccountTokenService: pretend.stub(
                    get_unverified_macaroon=(lambda: (macaroon, account_token))
                )
            }[iface]
        )

        authz_policy = auth_policy.AccountTokenAuthorizationPolicy(
            pretend.stub(permits=(lambda *args, **kwargs: "allow"))
        )

        assert (
            authz_policy.permits(pretend.stub(), pretend.stub(), pretend.stub())
            == "allow"
        )

        # Make sure we allow first-party and third-party caveats
        macaroon.add_first_party_caveat("first party caveat")

        macaroon.add_third_party_caveat(
            location="mysite.com", key="anykey", key_id="anykeyid"
        )

        assert (
            authz_policy.permits(pretend.stub(), pretend.stub(), pretend.stub())
            == "allow"
        )

    def test_missing_macaroon(self, monkeypatch):
        monkeypatch.setattr(auth_policy, "get_current_request", lambda: request)

        request = pretend.stub(
            find_service=lambda iface, **kw: {
                IAccountTokenService: pretend.stub(
                    get_unverified_macaroon=(lambda: (None, None))
                )
            }[iface]
        )

        authz_policy = auth_policy.AccountTokenAuthorizationPolicy(
            pretend.stub(permits=(lambda *args, **kwargs: "allow"))
        )

        assert (
            authz_policy.permits(pretend.stub(), pretend.stub(), pretend.stub())
            == "allow"
        )

    def test_principals_allowed_by_permission(self):
        authz_policy = auth_policy.AccountTokenAuthorizationPolicy(
            pretend.stub(principals_allowed_by_permission=(lambda a, b: (a, b)))
        )

        assert authz_policy.principals_allowed_by_permission(1, 2) == (1, 2)
