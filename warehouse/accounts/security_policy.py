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

from pyramid.authentication import (
    BasicAuthAuthenticationPolicy as _BasicAuthAuthenticationPolicy,
    SessionAuthenticationHelper,
)
from pyramid.interfaces import IAuthorizationPolicy, ISecurityPolicy
from pyramid.threadlocal import get_current_request
from zope.interface import implementer

from warehouse.accounts.interfaces import IUserService
from warehouse.cache.http import add_vary_callback
from warehouse.errors import WarehouseDenied
from warehouse.packaging.models import TwoFactorRequireable
from warehouse.utils.security_policy import ShimSecurityPolicy


class BasicAuthSecurityPolicy(ShimSecurityPolicy):
    pass


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
class SessionSecurityPolicy:
    def __init__(self, callback=None):
        self._session_helper = SessionAuthenticationHelper()
        self._callback = callback

    def unauthenticated_userid(self, request):
        # If we're calling into this API on a request, then we want to register
        # a callback which will ensure that the response varies based on the
        # Cookie header.
        request.add_response_callback(add_vary_callback("Cookie"))

        return self._session_helper.authenticated_userid(request)

    def identity(self, request):
        login_service = request.find_service(IUserService, context=None)
        user = login_service.get_user(self.unauthenticated_userid(request))
        if user is None:
            return None

        if self._callback is None:
            principals = _groupfinder(user)
        else:
            principals = self._callback(user.id, request)
            if principals is None:
                return None

            principals.extend(_groupfinder(user))

        return {"entity": user, "principals": principals}

    def forget(self, request, **kw):
        return self._session_helper.forget(request, **kw)

    def remember(self, request, userid, **kw):
        return self._session_helper.remember(request, userid, **kw)

    def permits(self, request, context, permission):
        return NotImplemented


class BasicAuthAuthenticationPolicy(_BasicAuthAuthenticationPolicy):
    def unauthenticated_userid(self, request):
        # If we're calling into this API on a request, then we want to register
        # a callback which will ensure that the response varies based on the
        # Authorization header.
        request.add_response_callback(add_vary_callback("Authorization"))

        # Dispatch to the real basic authentication policy
        username = super().unauthenticated_userid(request)

        # Assuming we got a username from the basic authentication policy, we
        # want to locate the userid from the IUserService.
        if username is not None:
            login_service = request.find_service(IUserService, context=None)
            return str(login_service.find_userid(username))


@implementer(IAuthorizationPolicy)
class TwoFactorAuthorizationPolicy:
    def __init__(self, policy):
        self.policy = policy

    def permits(self, context, principals, permission):
        # The Pyramid API doesn't let us access the request here, so we have to pull it
        # out of the thread local instead.
        # TODO: Work with Pyramid devs to figure out if there is a better way to support
        #       the worklow we are using here or not.
        request = get_current_request()

        # Our request could possibly be a None, if there isn't an active request, in
        # that case we're going to always deny, because without a request, we can't
        # determine if this request is authorized or not.
        if request is None:
            return WarehouseDenied(
                "There was no active request.", reason="no_active_request"
            )

        # Check if the subpolicy permits authorization
        subpolicy_permits = self.policy.permits(context, principals, permission)

        # If the request is permitted by the subpolicy, check if the context is
        # 2FA requireable, if 2FA is indeed required, and if the user has 2FA
        # enabled
        if subpolicy_permits and isinstance(context, TwoFactorRequireable):
            if (
                request.registry.settings["warehouse.two_factor_requirement.enabled"]
                and context.owners_require_2fa
                and not request.user.has_two_factor
            ):
                return WarehouseDenied(
                    "This project requires two factor authentication to be enabled "
                    "for all contributors.",
                    reason="owners_require_2fa",
                )
            if (
                request.registry.settings["warehouse.two_factor_mandate.enabled"]
                and context.pypi_mandates_2fa
                and not request.user.has_two_factor
            ):
                return WarehouseDenied(
                    "PyPI requires two factor authentication to be enabled "
                    "for all contributors to this project.",
                    reason="pypi_mandates_2fa",
                )
            if (
                request.registry.settings["warehouse.two_factor_mandate.available"]
                and context.pypi_mandates_2fa
                and not request.user.has_two_factor
            ):
                request.session.flash(
                    "This project is included in PyPI's two-factor mandate "
                    "for critical projects. In the future, you will be unable to "
                    "perform this action without enabling 2FA for your account",
                    queue="warning",
                )

        return subpolicy_permits

    def principals_allowed_by_permission(self, context, permission):
        # We just dispatch this, because this policy doesn't restrict what
        # principals are allowed by a particular permission, it just restricts
        # specific requests to not have that permission.
        return self.policy.principals_allowed_by_permission(context, permission)
