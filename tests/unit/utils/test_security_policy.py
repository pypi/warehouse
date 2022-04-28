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
from pyramid.security import Denied

from warehouse.utils import security_policy

from ...common.db.accounts import UserFactory


@pytest.mark.parametrize(
    (
        "is_superuser",
        "is_moderator",
        "is_psf_staff",
        "expected",
    ),
    [
        (False, False, False, []),
        (
            True,
            False,
            False,
            [
                "group:admins",
                "group:moderators",
                "group:psf_staff",
                "group:with_admin_dashboard_access",
            ],
        ),
        (
            False,
            True,
            False,
            ["group:moderators", "group:with_admin_dashboard_access"],
        ),
        (
            True,
            True,
            False,
            [
                "group:admins",
                "group:moderators",
                "group:psf_staff",
                "group:with_admin_dashboard_access",
            ],
        ),
        (
            False,
            False,
            True,
            ["group:psf_staff", "group:with_admin_dashboard_access"],
        ),
        (
            False,
            True,
            True,
            [
                "group:moderators",
                "group:psf_staff",
                "group:with_admin_dashboard_access",
            ],
        ),
    ],
)
def test_principals_for_authenticated_user(
    is_superuser,
    is_moderator,
    is_psf_staff,
    expected,
):
    user = pretend.stub(
        id=1,
        is_superuser=is_superuser,
        is_moderator=is_moderator,
        is_psf_staff=is_psf_staff,
    )
    assert security_policy._principals_for_authenticated_user(user) == expected


class TestMultiSecurityPolicy:
    def test_initializes(self):
        subpolicies = pretend.stub()
        authz = pretend.stub()
        policy = security_policy.MultiSecurityPolicy(subpolicies, authz)

        assert policy._policies is subpolicies
        assert policy._authz is authz

    def test_identity_none(self):
        subpolicies = [pretend.stub(identity=pretend.call_recorder(lambda r: None))]
        authz = pretend.stub()
        policy = security_policy.MultiSecurityPolicy(subpolicies, authz)

        request = pretend.stub()
        assert policy.identity(request) is None
        for p in subpolicies:
            assert p.identity.calls == [pretend.call(request)]

    def test_identity_first_come_first_serve(self):
        identity1 = pretend.stub()
        identity2 = pretend.stub()
        subpolicies = [
            pretend.stub(identity=pretend.call_recorder(lambda r: None)),
            pretend.stub(identity=pretend.call_recorder(lambda r: identity1)),
            pretend.stub(identity=pretend.call_recorder(lambda r: identity2)),
        ]
        authz = pretend.stub()
        policy = security_policy.MultiSecurityPolicy(subpolicies, authz)

        request = pretend.stub()
        assert policy.identity(request) is identity1
        assert subpolicies[0].identity.calls == [pretend.call(request)]
        assert subpolicies[1].identity.calls == [pretend.call(request)]
        assert subpolicies[2].identity.calls == []

    def test_authenticated_userid_no_identity(self):
        subpolicies = pretend.stub()
        authz = pretend.stub()
        policy = security_policy.MultiSecurityPolicy(subpolicies, authz)

        request = pretend.stub(identity=None)
        assert policy.authenticated_userid(request) is None

    def test_authenticated_userid_nonuser_identity(self, db_request):
        subpolicies = pretend.stub()
        authz = pretend.stub()
        policy = security_policy.MultiSecurityPolicy(subpolicies, authz)

        request = pretend.stub(identity=pretend.stub(id="fakeid"))
        assert policy.authenticated_userid(request) is None

    def test_authenticated_userid(self, db_request):
        subpolicies = pretend.stub()
        authz = pretend.stub()
        policy = security_policy.MultiSecurityPolicy(subpolicies, authz)

        user = UserFactory.create()
        request = pretend.stub(identity=user)
        assert policy.authenticated_userid(request) == str(user.id)

    def test_forget(self):
        header = pretend.stub()
        subpolicies = [
            pretend.stub(forget=pretend.call_recorder(lambda r, **kw: [header]))
        ]
        authz = pretend.stub()
        policy = security_policy.MultiSecurityPolicy(subpolicies, authz)

        request = pretend.stub()
        assert policy.forget(request, foo=None) == [header]
        assert subpolicies[0].forget.calls == [pretend.call(request, foo=None)]

    def test_remember(self):
        header = pretend.stub()
        subpolicies = [
            pretend.stub(remember=pretend.call_recorder(lambda r, uid, **kw: [header]))
        ]
        authz = pretend.stub()
        policy = security_policy.MultiSecurityPolicy(subpolicies, authz)

        request = pretend.stub()
        userid = pretend.stub()
        assert policy.remember(request, userid, foo=None) == [header]
        assert subpolicies[0].remember.calls == [
            pretend.call(request, userid, foo=None)
        ]

    def test_permits_user(self, db_request, monkeypatch):
        subpolicies = pretend.stub()
        status = pretend.stub()
        authz = pretend.stub(permits=pretend.call_recorder(lambda *a: status))
        policy = security_policy.MultiSecurityPolicy(subpolicies, authz)

        principals_for_authenticated_user = pretend.call_recorder(
            lambda *a: ["some:principal"]
        )
        monkeypatch.setattr(
            security_policy,
            "_principals_for_authenticated_user",
            principals_for_authenticated_user,
        )

        user = UserFactory.create()
        request = pretend.stub(identity=user)
        context = pretend.stub()
        permission = pretend.stub()
        assert policy.permits(request, context, permission) is status
        assert authz.permits.calls == [
            pretend.call(
                context,
                [Authenticated, f"user:{user.id}", "some:principal"],
                permission,
            )
        ]

    def test_permits_nonuser_denied(self):
        subpolicies = pretend.stub()
        authz = pretend.stub(permits=pretend.call_recorder(lambda *a: pretend.stub()))
        policy = security_policy.MultiSecurityPolicy(subpolicies, authz)

        # Anything that doesn't pass an isinstance check for User
        fakeuser = pretend.stub()
        request = pretend.stub(identity=fakeuser)
        context = pretend.stub()
        permission = pretend.stub()
        assert policy.permits(request, context, permission) == Denied("unimplemented")
        assert authz.permits.calls == []

    def test_permits_no_identity(self):
        subpolicies = pretend.stub()
        status = pretend.stub()
        authz = pretend.stub(permits=pretend.call_recorder(lambda *a: status))
        policy = security_policy.MultiSecurityPolicy(subpolicies, authz)

        request = pretend.stub(identity=None)
        context = pretend.stub()
        permission = pretend.stub()
        assert policy.permits(request, context, permission) is status
        assert authz.permits.calls == [pretend.call(context, [], permission)]
