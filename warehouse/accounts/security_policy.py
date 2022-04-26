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

import datetime

from pyramid.authentication import (
    SessionAuthenticationHelper,
    extract_http_basic_credentials,
)
from pyramid.httpexceptions import HTTPUnauthorized
from pyramid.interfaces import IAuthorizationPolicy, ISecurityPolicy
from pyramid.threadlocal import get_current_request
from zope.interface import implementer

from warehouse.accounts.interfaces import IPasswordBreachedService, IUserService
from warehouse.accounts.models import DisableReason
from warehouse.cache.http import add_vary_callback
from warehouse.email import send_password_compromised_email_hibp
from warehouse.errors import (
    BasicAuthAccountFrozen,
    BasicAuthBreachedPassword,
    BasicAuthFailedPassword,
    WarehouseDenied,
)
from warehouse.packaging.models import TwoFactorRequireable
from warehouse.utils.security_policy import AuthenticationMethod


def _format_exc_status(exc, message):
    exc.status = f"{exc.status_code} {message}"
    return exc


def _basic_auth_check(username, password, request):
    # Basic authentication can only be used for uploading
    if request.matched_route.name not in ["forklift.legacy.file_upload"]:
        return False

    login_service = request.find_service(IUserService, context=None)
    breach_service = request.find_service(IPasswordBreachedService, context=None)

    userid = login_service.find_userid(username)
    if userid is not None:
        user = login_service.get_user(userid)
        is_disabled, disabled_for = login_service.is_disabled(user.id)
        if is_disabled:
            # This technically violates the contract a little bit, this function is
            # meant to return False if the user cannot log in. However we want to
            # present a different error message than is normal when we're denying the
            # log in because of a compromised password. So to do that, we'll need to
            # raise a HTTPError that'll ultimately get returned to the client. This is
            # OK to do here because we've already successfully authenticated the
            # credentials, so it won't screw up the fall through to other authentication
            # mechanisms (since we wouldn't have fell through to them anyways).
            if disabled_for == DisableReason.CompromisedPassword:
                raise _format_exc_status(
                    BasicAuthBreachedPassword(), breach_service.failure_message_plain
                )
            elif disabled_for == DisableReason.AccountFrozen:
                raise _format_exc_status(BasicAuthAccountFrozen(), "Account is frozen.")
            else:
                raise _format_exc_status(HTTPUnauthorized(), "Account is disabled.")
        elif login_service.check_password(
            user.id,
            password,
            tags=["mechanism:basic_auth", "method:auth", "auth_method:basic"],
        ):
            if breach_service.check_password(
                password, tags=["method:auth", "auth_method:basic"]
            ):
                send_password_compromised_email_hibp(request, user)
                login_service.disable_password(
                    user.id, reason=DisableReason.CompromisedPassword
                )
                raise _format_exc_status(
                    BasicAuthBreachedPassword(), breach_service.failure_message_plain
                )

            login_service.update_user(user.id, last_login=datetime.datetime.utcnow())
            return True
        else:
            user.record_event(
                tag="account:login:failure",
                ip_address=request.remote_addr,
                additional={"reason": "invalid_password", "auth_method": "basic"},
            )
            raise _format_exc_status(
                BasicAuthFailedPassword(),
                "Invalid or non-existent authentication information. "
                "See {projecthelp} for more information.".format(
                    projecthelp=request.help_url(_anchor="invalid-auth")
                ),
            )

    # No user, no authentication.
    return False


@implementer(ISecurityPolicy)
class SessionSecurityPolicy:
    def __init__(self):
        self._session_helper = SessionAuthenticationHelper()

    def identity(self, request):
        # If we're calling into this API on a request, then we want to register
        # a callback which will ensure that the response varies based on the
        # Cookie header.
        request.add_response_callback(add_vary_callback("Cookie"))
        request.authentication_method = AuthenticationMethod.SESSION

        userid = self._session_helper.authenticated_userid(request)
        if userid is None:
            return None

        # Session authentication cannot be used for uploading
        if request.matched_route.name in ["forklift.legacy.file_upload"]:
            return None

        login_service = request.find_service(IUserService, context=None)

        # Our session might be "valid" despite predating a password change.
        if request.session.password_outdated(
            login_service.get_password_timestamp(userid)
        ):
            request.session.invalidate()
            request.session.flash(
                "Session invalidated by password change", queue="error"
            )
            return None

        # Sessions can only authenticate users, not any other type of identity.
        return login_service.get_user(userid)

    def forget(self, request, **kw):
        return self._session_helper.forget(request, **kw)

    def remember(self, request, userid, **kw):
        return self._session_helper.remember(request, userid, **kw)

    def authenticated_userid(self, request):
        # Handled by MultiSecurityPolicy
        return NotImplemented

    def permits(self, request, context, permission):
        # Handled by MultiSecurityPolicy
        return NotImplemented


@implementer(ISecurityPolicy)
class BasicAuthSecurityPolicy:
    def identity(self, request):
        # If we're calling into this API on a request, then we want to register
        # a callback which will ensure that the response varies based on the
        # Authorization header.
        request.add_response_callback(add_vary_callback("Authorization"))
        request.authentication_method = AuthenticationMethod.BASIC_AUTH

        credentials = extract_http_basic_credentials(request)
        if credentials is None:
            return None

        username, password = credentials
        if not _basic_auth_check(username, password, request):
            return None

        # Like sessions; basic auth can only authenticate users.
        login_service = request.find_service(IUserService, context=None)
        return login_service.get_user_by_username(username)

    def forget(self, request, **kw):
        # No-op.
        return []

    def remember(self, request, userid, **kw):
        # NOTE: We could make realm configurable here.
        return [("WWW-Authenticate", 'Basic realm="Realm"')]

    def authenticated_userid(self, request):
        # Handled by MultiSecurityPolicy
        return NotImplemented

    def permits(self, request, context, permission):
        # Handled by MultiSecurityPolicy
        return NotImplemented


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
