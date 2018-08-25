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
from pyramid import authentication
from pyramid.interfaces import IAuthenticationPolicy
from zope.interface.verify import verifyClass

from warehouse.accounts import auth_policy
from warehouse.accounts.interfaces import IUserService

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
        assert isinstance(
            auth_policy.AccountTokenAuthenticationPolicy(pretend.stub()),
            authentication.CallbackAuthenticationPolicy,
        )

    def test_account_token_routes_allowed(self):
        request = pretend.stub(matched_route=pretend.stub(name="not_a_real_route"))

        policy = auth_policy.AccountTokenAuthenticationPolicy(pretend.stub())
        assert policy.unauthenticated_userid(request) is None

    def test_account_token_required_parameter(self):
        request = pretend.stub(
            matched_route=pretend.stub(name="forklift.legacy.file_upload"), params={}
        )

        policy = auth_policy.AccountTokenAuthenticationPolicy(pretend.stub())
        assert policy.unauthenticated_userid(request) is None

    def test_account_token_malformed(self):
        request = pretend.stub(
            matched_route=pretend.stub(name="forklift.legacy.file_upload"),
            params={"account_token": "DEADBEEF"},
        )

        policy = auth_policy.AccountTokenAuthenticationPolicy(pretend.stub())
        assert policy.unauthenticated_userid(request) is None

    def test_account_token_bad_settings(self):
        # Test bad location
        macaroon = Macaroon(
            location="notpypi.org", identifier="example_id", key="example_secret"
        )

        request = pretend.stub(
            matched_route=pretend.stub(name="forklift.legacy.file_upload"),
            params={"account_token": macaroon.serialize()},
            registry=pretend.stub(
                settings={
                    "account_token.id": "example_id",
                    "account_token.secret": "example_secret",
                }
            ),
        )

        policy = auth_policy.AccountTokenAuthenticationPolicy(pretend.stub())
        assert policy.unauthenticated_userid(request) is None

        # Test bad identifier
        macaroon = Macaroon(
            location="pypi.org", identifier="bad_id", key="example_secret"
        )

        request.params["account_token"] = macaroon.serialize()
        policy = auth_policy.AccountTokenAuthenticationPolicy(pretend.stub())
        assert policy.unauthenticated_userid(request) is None

        # Tamper with macaroon
        macaroon = Macaroon(
            location="pypi.org", identifier="example_id", key="example_secret"
        )

        serialized = macaroon.serialize()

        request.params["account_token"] = "".join(
            (serialized[:-8], "AAAAAAA", serialized[-1:])
        )
        assert policy.unauthenticated_userid(request) is None

    def test_account_token_with_no_user(self, db_request):
        macaroon = Macaroon(
            location="pypi.org", identifier="example_id", key="example_secret"
        )

        request = pretend.stub(
            find_service=lambda iface, **kw: {
                IUserService: pretend.stub(find_userid_by_account_token=pretend.stub())
            }[iface],
            params={"account_token": macaroon.serialize()},
            registry=pretend.stub(
                settings={
                    "account_token.id": "example_id",
                    "account_token.secret": "example_secret",
                }
            ),
            matched_route=pretend.stub(name="forklift.legacy.file_upload"),
            db=db_request,
            session={},
        )

        policy = auth_policy.AccountTokenAuthenticationPolicy(pretend.stub())
        assert policy.unauthenticated_userid(request) is None

    def test_account_token_auth(self, db_request):
        # Test basic happy path
        user = UserFactory.create(username="test_user")
        account_token = AccountTokenFactory.create(username=user.username)
        account_token_id = str(account_token.id)

        macaroon = Macaroon(
            location="pypi.org", identifier="example_id", key="example_secret"
        )

        macaroon.add_first_party_caveat(f"id: {account_token_id}")

        request = pretend.stub(
            find_service=lambda iface, **kw: {
                IUserService: pretend.stub(
                    find_userid_by_account_token=(
                        lambda x: user.id if x == account_token_id else None
                    )
                )
            }[iface],
            params={"account_token": macaroon.serialize()},
            registry=pretend.stub(
                settings={
                    "account_token.id": "example_id",
                    "account_token.secret": "example_secret",
                }
            ),
            matched_route=pretend.stub(name="forklift.legacy.file_upload"),
            db=db_request,
            session={},
        )

        policy = auth_policy.AccountTokenAuthenticationPolicy(pretend.stub())
        assert policy.unauthenticated_userid(request) == user.id

        # Test package caveats
        macaroon.add_first_party_caveat("package: pyexample")
        macaroon.add_third_party_caveat(
            location="mysite.com", key="anykey", key_id="anykeyid"
        )
        request.params["account_token"] = macaroon.serialize()
        request.session["account_token_package"] = None

        assert policy.unauthenticated_userid(request) == user.id
        assert request.session["account_token_package"] == "pyexample"

        # Ensure you can't overwrite previous caveats
        takeover_user = UserFactory.create(username="takeover_user")
        takeover_account_token = AccountTokenFactory.create(
            username=takeover_user.username
        )
        takeover_account_token_id = str(takeover_account_token.id)

        macaroon.add_first_party_caveat(f"id: {takeover_account_token_id}")
        macaroon.add_first_party_caveat("package: additionalpackage")

        request.params["account_token"] = macaroon.serialize()
        request.session["account_token_package"] = None

        assert policy.unauthenticated_userid(request) == user.id
        assert request.session["account_token_package"] == "pyexample"

    def test_first_party_caveat_validation(self):
        policy = auth_policy.AccountTokenAuthenticationPolicy(pretend.stub())

        assert policy._validate_first_party_caveat("id")
        assert policy._validate_first_party_caveat("package")
        assert not policy._validate_first_party_caveat("not_valid")

    def test_account_token_interface(self):
        def _authenticate(a, b):
            return a, b

        policy = auth_policy.AccountTokenAuthenticationPolicy(_authenticate)

        assert policy.remember("", "") == []
        assert policy.forget("") == []
        assert policy._auth_callback(1, 2) == (1, 2)
