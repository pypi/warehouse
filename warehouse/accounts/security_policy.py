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
from pyramid.authorization import ACLHelper
from pyramid.httpexceptions import HTTPUnauthorized
from pyramid.interfaces import ISecurityPolicy
from pyramid.security import Allowed
from zope.interface import implementer

from warehouse import perms
from warehouse.accounts.interfaces import IPasswordBreachedService, IUserService
from warehouse.accounts.models import DisableReason, User
from warehouse.cache.http import add_vary_callback
from warehouse.email import send_password_compromised_email_hibp
from warehouse.errors import (
    BasicAuthAccountFrozen,
    BasicAuthBreachedPassword,
    BasicAuthFailedPassword,
    WarehouseDenied,
)
from warehouse.events.tags import EventTag
from warehouse.packaging.models import TwoFactorRequireable
from warehouse.utils.security_policy import AuthenticationMethod, principals_for


def _format_exc_status(exc, message):
    exc.status = f"{exc.status_code} {message}"
    return exc


def _basic_auth_check(username, password, request):
    login_service = request.find_service(IUserService, context=None)
    breach_service = request.find_service(IPasswordBreachedService, context=None)

    userid = login_service.find_userid(username)
    request._unauthenticated_userid = userid
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
                    user.id,
                    request,
                    reason=DisableReason.CompromisedPassword,
                )
                raise _format_exc_status(
                    BasicAuthBreachedPassword(), breach_service.failure_message_plain
                )

            login_service.update_user(user.id, last_login=datetime.datetime.utcnow())
            user.record_event(
                tag=EventTag.Account.LoginSuccess,
                ip_address=request.remote_addr,
                request=request,
                additional={"auth_method": "basic"},
            )
            return True
        else:
            user.record_event(
                tag=EventTag.Account.LoginFailure,
                ip_address=request.remote_addr,
                request=request,
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
        self._acl = ACLHelper()

    def identity(self, request):
        # If our current request *is* any API request, then we will disallow
        # authenticating with sessions, as an API request should only use API
        # authentication methods.
        if request.is_api:
            return None

        # If we're calling into this API on a request, then we want to register
        # a callback which will ensure that the response varies based on the
        # Cookie header.
        request.add_response_callback(add_vary_callback("Cookie"))
        request.authentication_method = AuthenticationMethod.SESSION

        if request.banned.by_ip(request.remote_addr):
            return None

        userid = self._session_helper.authenticated_userid(request)
        request._unauthenticated_userid = userid

        if userid is None:
            return None

        login_service = request.find_service(IUserService, context=None)

        # A user might delete their account and immediately issue a request
        # while the deletion is processing, causing the session check
        # (via authenticated_userid above) to pass despite the user no longer
        # existing. We catch that here to avoid raising during the password
        # staleness check immediately below.
        user = login_service.get_user(userid)
        if user is None:
            return None

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
        return user

    def forget(self, request, **kw):
        return self._session_helper.forget(request, **kw)

    def remember(self, request, userid, **kw):
        return self._session_helper.remember(request, userid, **kw)

    def authenticated_userid(self, request):
        # Handled by MultiSecurityPolicy
        raise NotImplementedError

    def permits(self, request, context, permission):
        return _permits_for_user_policy(self._acl, request, context, permission)


@implementer(ISecurityPolicy)
class BasicAuthSecurityPolicy:
    def __init__(self):
        self._acl = ACLHelper()

    def identity(self, request):
        # If our current request isn't an API request, then we'll just quickly skip
        # trying to do anything since we only support basic auth on API routes.
        # NOTE: Technically we only support it on upload, which is at the moment our
        #       only API route. We'll end up removing this entirely once we go to 2FA
        #       only for uploading, so a short term window if we add another API route
        #       seems fine.
        if not request.is_api:
            return None

        # If we're calling into this API on a request, then we want to register
        # a callback which will ensure that the response varies based on the
        # Authorization header.
        request.add_response_callback(add_vary_callback("Authorization"))
        request.authentication_method = AuthenticationMethod.BASIC_AUTH

        if request.banned.by_ip(request.remote_addr):
            return None

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
        raise NotImplementedError

    def permits(self, request, context, permission):
        return _permits_for_user_policy(self._acl, request, context, permission)


def _permits_for_user_policy(acl, request, context, permission):
    # It should only be possible for request.identity to be a User object
    # at this point, and we only a User in these policies.
    assert isinstance(request.identity, User)

    # Check if our permission requires MFA, and if it does does our user have MFA.
    # We check this prior to authorizing the request, because there is nothing context
    # sensitive and this lets us skip checking the ACL if we're going to fail due to
    # MFA anyways.
    if perms.requires_2fa(permission) and not request.identity.has_two_factor:
        return WarehouseDenied(
            "This action requires two factor authentication.",
            reason="requires_2fa",
        )

    # Dispatch to our ACL
    # NOTE: These parameters are in a different order
    res = acl.permits(context, principals_for(request.identity), permission)

    # If our underlying permits allowed this, we will check our 2FA status,
    # that might possibly return a reason to deny the request anyways, and if
    # it does we'll return that.
    if isinstance(res, Allowed):
        # Check if the context object requires MFA, whether from PyPI or from the
        # owner of the context requiring it. We check this after we've checked the
        # ACL to avoid leaking whether a project requires MFA or not.
        # NOTE: This check should eventually go away once we requires 2FA across the
        #       entire site.
        mfa = _check_for_mfa(request, context)
        if mfa is not None:
            return mfa

    return res


def _check_for_mfa(request, context) -> WarehouseDenied | None:
    # It should only be possible for request.identity to be a User object
    # at this point, and we only a User in these policies.
    assert isinstance(request.identity, User)

    # Check if the context is 2FA requireable, if 2FA is indeed required, and if
    # the user has 2FA enabled.
    if isinstance(context, TwoFactorRequireable):
        # Check if we allow owners to require 2FA, and if so does our context owner
        # require 2FA? And if so does our user have 2FA?
        if (
            request.registry.settings["warehouse.two_factor_requirement.enabled"]
            and context.owners_require_2fa
            and not request.identity.has_two_factor
        ):
            return WarehouseDenied(
                "This project requires two factor authentication to be enabled "
                "for all contributors.",
                reason="owners_require_2fa",
            )

        # Check if PyPI is enforcing the 2FA mandate on "critical" projects, and if it
        # is does our current context require it, and if it does, does our user have
        # 2FA?
        if (
            request.registry.settings["warehouse.two_factor_mandate.enabled"]
            and context.pypi_mandates_2fa
            and not request.identity.has_two_factor
        ):
            return WarehouseDenied(
                "PyPI requires two factor authentication to be enabled "
                "for all contributors to this project.",
                reason="pypi_mandates_2fa",
            )

        # Check if PyPI's 2FA mandate is available, but not enforcing, and if it is and
        # the current context would require 2FA, and if our user doesn't have have 2FA
        # then we'll flash a warning.
        if (
            request.registry.settings["warehouse.two_factor_mandate.available"]
            and context.pypi_mandates_2fa
            and not request.identity.has_two_factor
        ):
            request.session.flash(
                "This project is included in PyPI's two-factor mandate "
                "for critical projects. In the future, you will be unable to "
                "perform this action without enabling 2FA for your account",
                queue="warning",
            )

    return None
