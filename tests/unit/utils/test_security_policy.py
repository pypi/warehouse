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

from pyramid.authorization import Authenticated
from pyramid.security import Allowed, Denied
from zope.interface.verify import verifyClass
from pyramid.interfaces import ISecurityPolicy

from warehouse.oidc.utils import OIDCContext
from warehouse.utils import security_policy

from ...common.db.accounts import UserFactory
from ...common.db.oidc import GitHubPublisherFactory


def test_principals_for():
    identity = pretend.stub(__principals__=lambda: ["a", "b", "z"])
    assert security_policy.principals_for(identity) == ["a", "b", "z"]


class TestMultiSecurityPolicy:
    def test_verify(self):
        assert verifyClass(
            ISecurityPolicy,
            security_policy.MultiSecurityPolicy,
        )

    def test_identity_none(self):
        subpolicies = [pretend.stub(identity=lambda r: None)]
        policy = security_policy.MultiSecurityPolicy(subpolicies)

        request = pretend.stub(add_finished_callback=lambda *a, **kw: None)
        assert policy.identity(request) is None

    def test_identity_first_come_first_serve(self):
        identity1 = pretend.stub()
        identity2 = pretend.stub()
        subpolicies = [
            pretend.stub(identity=lambda r: None),
            pretend.stub(identity=lambda r: identity1),
            pretend.stub(identity=lambda r: identity2),
        ]
        policy = security_policy.MultiSecurityPolicy(subpolicies)

        request = pretend.stub(add_finished_callback=lambda *a, **kw: None)
        assert policy.identity(request) is identity1

    def test_authenticated_userid_no_identity(self):
        request = pretend.stub(add_finished_callback=lambda *a, **kw: None)
        subpolicies = [pretend.stub(identity=lambda r: None)]
        policy = security_policy.MultiSecurityPolicy(subpolicies)

        assert policy.authenticated_userid(request) is None

    def test_authenticated_userid_nonuser_identity(self, db_request):
        request = pretend.stub(add_finished_callback=lambda *a, **kw: None)
        nonuser = pretend.stub(id="not-a-user-instance")
        subpolicies = [pretend.stub(identity=lambda r: nonuser)]
        policy = security_policy.MultiSecurityPolicy(subpolicies)

        assert policy.authenticated_userid(request) is None

    def test_authenticated_userid(self, monkeypatch):
        monkeypatch.setattr(security_policy, "User", pretend.stub)

        request = pretend.stub(add_finished_callback=lambda *a, **kw: None)
        user = pretend.stub(id="a fake user")
        subpolicies = [pretend.stub(identity=lambda r: user)]
        policy = security_policy.MultiSecurityPolicy(subpolicies)

        assert policy.authenticated_userid(request) == str(user.id)

    def test_forget(self):
        subpolicies = [pretend.stub(forget=lambda r, **kw: [("ForgetMe", "1")])]
        policy = security_policy.MultiSecurityPolicy(subpolicies)

        request = pretend.stub()
        assert policy.forget(request, foo=None) == [("ForgetMe", "1")]

    def test_remember(self):
        header = pretend.stub()
        subpolicies = [
            pretend.stub(remember=lambda r, uid, foo, **kw: [("RememberMe", foo)])
        ]
        policy = security_policy.MultiSecurityPolicy(subpolicies)

        request = pretend.stub()
        userid = pretend.stub()
        assert policy.remember(request, userid, foo="bob") == [("RememberMe", "bob")]
