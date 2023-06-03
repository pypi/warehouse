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

from pyramid.authorization import ACLHelper, Authenticated
from pyramid.interfaces import ISecurityPolicy
from pyramid.security import Denied
from zope.interface import implementer

from warehouse.accounts.models import User
from warehouse.oidc.utils import OIDCContext


class AuthenticationMethod(enum.Enum):
    BASIC_AUTH = "basic-auth"
    SESSION = "session"
    MACAROON = "macaroon"


class IdentityContext:
    """
    A wrapper that contains either a `OIDCContext` or `User`.

    Returned by `MultiSecurityPolicy.identity`.
    """

    _user: User | None = None
    _oidc: OIDCContext | None = None

    def __init__(self, identity, policy):
        if isinstance(identity, User):
            self._user = identity
        elif isinstance(identity, OIDCContext):
            self._oidc = identity

        self._policy = policy

    @property
    def user(self):
        return self._user

    @property
    def oidc_publisher(self):
        return self._oidc.publisher if self._oidc else None

    @property
    def oidc_claims(self):
        return self._oidc.claims if self._oidc else None

    @property
    def policy(self):
        return self._policy


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
    * `authenticated_userid`: Selected from the first policy to return a user
    * `forget`: Combined from all policies
    * `remember`: Combined from all policies
    * `permits`: Uses the AuthZ policy passed during initialization

    These semantics mostly mirror those of `pyramid-multiauth`.
    """

    def __init__(self, policies):
        self._policies = policies
        self._acl = ACLHelper()

    def identity(self, request):
        for policy in self._policies:
            if ident := policy.identity(request):
                return IdentityContext(ident, policy)

        return None

    def authenticated_userid(self, request):
        if ident := self.identity(request):
            if ident.user:
                return str(ident.user.id)
        return None

    def unauthenticated_userid(self, request):
        # This is deprecated and we shouldn't use it
        raise NotImplementedError

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
        # First, check if our bound subpolicy denies the request.
        identity = self.identity(request)
        if identity and not (permits := identity.policy.permits(request, context, permission)):
            return permits

        # Next, construct a list of principals from our request.
        principals = []
        if identity is not None:
            principals.append(Authenticated)

            if identity.user:
                principals.append(f"user:{identity.user.id}")
                principals.extend(_principals_for_authenticated_user(identity.user))
            elif identity.oidc_publisher:
                principals.append(f"oidc:{identity.oidc_publisher.id}")
            else:
                return Denied("unknown identity")

        # Finally, check the principals against the context.
        return self._acl.permits(context, principals, permission)
