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

from pyramid.interfaces import IAuthenticationPolicy
from zope.interface.verify import verifyClass

from warehouse.accounts.auth_policy import BasicAuthAuthenticationPolicy
from warehouse.accounts.interfaces import ILoginService


class TestBasicAuthAuthenticationPolicy:

    def test_verify(self):
        assert verifyClass(
            IAuthenticationPolicy,
            BasicAuthAuthenticationPolicy,
        )

    def test_unauthenticated_userid_no_userid(self):
        policy = BasicAuthAuthenticationPolicy(check=pretend.stub())
        policy._get_credentials = pretend.call_recorder(lambda request: None)

        request = pretend.stub()

        assert policy.unauthenticated_userid(request) is None
        assert policy._get_credentials.calls == [pretend.call(request)]

    def test_unauthenticated_userid_with_userid(self):
        policy = BasicAuthAuthenticationPolicy(check=pretend.stub())
        policy._get_credentials = pretend.call_recorder(
            lambda request: ("username", "password")
        )

        userid = pretend.stub()
        service = pretend.stub(
            find_userid=pretend.call_recorder(lambda username: userid),
        )
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda iface, context: service)
        )

        assert policy.unauthenticated_userid(request) is userid
        assert request.find_service.calls == [
            pretend.call(ILoginService, context=None),
        ]
        assert service.find_userid.calls == [pretend.call("username")]
