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

from pyramid import authentication
from pyramid.interfaces import IAuthenticationPolicy
from zope.interface.verify import verifyClass

from warehouse.accounts import auth_policy
from warehouse.accounts.interfaces import IUserService


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
