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

from pyramid.interfaces import ISecurityPolicy
from zope.interface.verify import verifyClass

from tests.common.db.accounts import UserFactory
from warehouse.accounts.utils import UserContext
from warehouse.utils import security_policy


def test_principals_for():
    identity = pretend.stub(__principals__=lambda: ["a", "b", "z"])
    assert security_policy.principals_for(identity) == ["a", "b", "z"]


def test_principals_for_with_none():
    assert security_policy.principals_for(pretend.stub()) == []


class TestMultiSecurityPolicy:
    def test_verify(self):
        assert verifyClass(
            ISecurityPolicy,
            security_policy.MultiSecurityPolicy,
        )

    def test_reset(self):
        identity1 = pretend.stub()
        identity2 = pretend.stub()
        identities = iter([identity1, identity2])

        subpolicies = [pretend.stub(identity=lambda r: next(identities))]
        policy = security_policy.MultiSecurityPolicy(subpolicies)

        request = pretend.stub(add_finished_callback=lambda *a, **kw: None)

        assert policy.identity(request) is identity1
        assert policy.identity(request) is identity1

        policy.reset(request)

        assert policy.identity(request) is identity2

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

    def test_authenticated_userid_user_contex_macaroon(self, db_request):
        user = UserFactory.create()
        user_ctx = UserContext(user, pretend.stub())

        request = pretend.stub(add_finished_callback=lambda *a, **kw: None)
        subpolicies = [pretend.stub(identity=lambda r: user_ctx)]
        policy = security_policy.MultiSecurityPolicy(subpolicies)

        assert (
            policy.authenticated_userid(request)
            == str(user.id)
            == str(user_ctx.user.id)
        )

    def test_authenticated_userid_user_context_no_macaroon(self, db_request):
        user = UserFactory.create()
        user_ctx = UserContext(user, None)

        request = pretend.stub(add_finished_callback=lambda *a, **kw: None)
        subpolicies = [pretend.stub(identity=lambda r: user_ctx)]
        policy = security_policy.MultiSecurityPolicy(subpolicies)

        assert policy.authenticated_userid(request) == str(user.id)

    def test_forget(self):
        subpolicies = [pretend.stub(forget=lambda r, **kw: [("ForgetMe", "1")])]
        policy = security_policy.MultiSecurityPolicy(subpolicies)

        request = pretend.stub()
        assert policy.forget(request, foo=None) == [("ForgetMe", "1")]

    def test_remember(self):
        subpolicies = [
            pretend.stub(remember=lambda r, uid, foo, **kw: [("RememberMe", foo)])
        ]
        policy = security_policy.MultiSecurityPolicy(subpolicies)

        request = pretend.stub()
        userid = pretend.stub()
        assert policy.remember(request, userid, foo="bob") == [("RememberMe", "bob")]

    def test_permits(self):
        identity1 = pretend.stub()
        identity2 = pretend.stub()
        context = pretend.stub()

        subpolicies = [
            pretend.stub(identity=lambda r: None),
            pretend.stub(
                identity=lambda r: identity1,
                permits=(
                    lambda r, c, p: r.identity == identity1
                    and c == context
                    and p == "myperm"
                ),
            ),
            pretend.stub(identity=lambda r: identity2),
        ]
        policy = security_policy.MultiSecurityPolicy(subpolicies)

        request = pretend.stub(
            identity=identity1,
            add_finished_callback=lambda *a, **kw: None,
        )

        assert policy.permits(request, context, "myperm")

    def test_permits_no_policy(self):
        subpolicies = [
            pretend.stub(identity=lambda r: None),
            pretend.stub(identity=lambda r: None),
            pretend.stub(identity=lambda r: None),
        ]
        policy = security_policy.MultiSecurityPolicy(subpolicies)
        request = pretend.stub(
            identity=None, add_finished_callback=lambda *a, **kw: None
        )
        context = pretend.stub()

        assert not policy.permits(request, context, "myperm")
