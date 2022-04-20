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

from pyramid.authorization import Authenticated, Everyone
from pyramid.interfaces import ISecurityPolicy
from zope.interface import implementer

from warehouse.accounts.interfaces import IUserService


def _groupfinder(user):
    principals = []

    if user.is_superuser:
        principals.append("group:admins")
    if user.is_moderator or user.is_superuser:
        principals.append("group:moderators")
    if user.is_psf_staff or user.is_superuser:
        principals.append("group:psf_staff")

    # user must have base admin access if any admin permission
    if principals:
        principals.append("group:with_admin_dashboard_access")

    return principals


@implementer(ISecurityPolicy)
class ShimSecurityPolicy:
    """
    Modified from the Pyramid changelog:
    https://docs.pylonsproject.org/projects/pyramid/en/latest/whatsnew-2.0.html

    Unlike the Pyramid example, this `ShimSecurityPolicy` does not pass through
    to an underlying AuthZ policy. AuthZ is handled separately.
    """

    def __init__(self, authn_policy):
        self.authn_policy = authn_policy

    def authenticated_userid(self, request):
        return self.authn_policy.authenticated_userid(request)

    def identity(self, request):
        login_service = request.find_service(IUserService, context=None)
        user = login_service.get_user(self.authenticated_userid(request))
        if user is not None:
            return {"entity": user, "principals": _groupfinder(user)}
        return None

    def permits(self, request, context, permission):
        return NotImplemented

    def remember(self, request, userid, **kw):
        return self.authn_policy.remember(request, userid, **kw)

    def forget(self, request, **kw):
        return self.authn_policy.forget(request, **kw)


@implementer(ISecurityPolicy)
class MultiSecurityPolicy:
    """
    A wrapper for multiple Pyramid 2.0-style "security policies", which replace
    Pyramid 1.0's separate AuthN and AuthZ APIs.

    Security policies are checked in the order provided during initialization,
    with the following semantics:

    * `identity`: Selected from the first policy to return non-`None`
    * `authenticated_userid`: Selected from the request identity, if present
    * `forget`: Combined from all policies
    * `remember`: Combined from all policies
    * `permits`: Uses the AuthZ policy passed during initialization

    These semantics mostly mirror those of `pyramid-multiauth`.
    """

    def __init__(self, policies, authz):
        self._policies = policies
        self._authz = authz

    def identity(self, request):
        for policy in self._policies:
            if ident := policy.identity(request):
                return ident

        return None

    def authenticated_userid(self, request):
        if request.identity:
            return str(request.identity["entity"].id)
        return None

    def forget(self, request, **kw):
        headers = []
        for policy in self._policies:
            headers.extend(policy.forget(request, **kw))
        return headers

    def remember(self, request, userid, **kw):
        headers = []
        for policy in self._policies:
            headers.extend(policy.remember(request, userid, **kw))
        return headers

    def permits(self, request, context, permission):
        identity = request.identity
        principals = [Everyone]
        if identity is not None:
            principals.extend(
                [Authenticated, str(identity["entity"].id), identity["principals"]]
            )
        return self._authz.permits(context, principals, permission)
