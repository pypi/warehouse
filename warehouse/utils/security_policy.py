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

import enum

from pyramid.authorization import Authenticated
from pyramid.interfaces import ISecurityPolicy
from pyramid.security import Denied
from zope.interface import implementer

from warehouse.accounts.models import User


class AuthenticationMethod(enum.Enum):
    BASIC_AUTH = "basic-auth"
    SESSION = "session"
    MACAROON = "macaroon"


def _principals_for_authenticated_user(user):
    """Apply the necessary principals to the authenticated user"""
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
        if request.identity and isinstance(request.identity, User):
            return str(request.identity.id)
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
        principals = []
        if identity is not None:
            principals.append(Authenticated)

            if isinstance(identity, User):
                principals.append(f"user:{identity.id}")
                principals.extend(_principals_for_authenticated_user(identity))
            else:
                return Denied("unimplemented")

        # NOTE: Observe that the parameters passed into the underlying AuthZ
        # policy here are not the same (or in the same order) as the ones
        # passed into `permits` above. This is because the underlying AuthZ
        # policy is a "legacy" Pyramid 1.0 style one that implements the
        # `IAuthorizationPolicy` interface rather than `ISecurityPolicy`.
        return self._authz.permits(context, principals, permission)
