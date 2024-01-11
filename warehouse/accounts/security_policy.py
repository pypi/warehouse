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
    SessionAuthenticationHelper,
    extract_http_basic_credentials,
)
from pyramid.authorization import ACLHelper
from pyramid.httpexceptions import HTTPForbidden
from pyramid.interfaces import ISecurityPolicy
from pyramid.security import Allowed
from zope.interface import implementer

from warehouse.accounts.interfaces import IUserService
from warehouse.accounts.models import User
from warehouse.cache.http import add_vary_callback
from warehouse.errors import WarehouseDenied
from warehouse.utils.security_policy import AuthenticationMethod, principals_for


def _format_exc_status(exc, message):
    exc.status = f"{exc.status_code} {message}"
    return exc


@implementer(ISecurityPolicy)
class SessionSecurityPolicy:
    def __init__(self):
        self._session_helper = SessionAuthenticationHelper()
        self._acl = ACLHelper()

    def identity(self, request):
        # If we're calling into this API on a request, then we want to register
        # a callback which will ensure that the response varies based on the
        # Cookie header.
        request.add_response_callback(add_vary_callback("Cookie"))
        request.authentication_method = AuthenticationMethod.SESSION

        if request.banned.by_ip(request.remote_addr):
            return None

        # A route must be matched
        if not request.matched_route:
            return None

        # Session authentication cannot be used for uploading
        if request.matched_route.name == "forklift.legacy.file_upload":
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

        # User may have been frozen or disabled since the session was created.
        is_disabled, _ = login_service.is_disabled(userid)
        if is_disabled:
            request.session.invalidate()
            request.session.flash("Session invalidated", queue="error")
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
    """The BasicAuthSecurityPolicy is no longer allowed
    and raises a message when used for uploads when it's not an API Token"""

    def identity(self, request):
        # If we're calling into this API on a request, then we want to register
        # a callback which will ensure that the response varies based on the
        # Authorization header.
        request.add_response_callback(add_vary_callback("Authorization"))
        request.authentication_method = AuthenticationMethod.BASIC_AUTH

        if not request.matched_route:
            return None
        if request.matched_route.name != "forklift.legacy.file_upload":
            return None

        credentials = extract_http_basic_credentials(request)
        if credentials is None:
            return None

        username, _password = credentials

        # The API Token username is allowed to pass through to the
        # MacaroonSecurityPolicy.
        if username == "__token__":
            return None

        raise _format_exc_status(
            HTTPForbidden(),
            "Username/Password authentication is no longer supported. "
            "Migrate to API Tokens or Trusted Publishers instead. "
            f"See {request.help_url(_anchor='apitoken')} "
            f"and {request.help_url(_anchor='trusted-publishers')}",
        )

    def forget(self, request, **kw):
        # No-op.
        return []

    def remember(self, request, userid, **kw):
        # No-op.
        return []

    def authenticated_userid(self, request):
        raise NotImplementedError

    def permits(self, request, context, permission):
        raise NotImplementedError


def _permits_for_user_policy(acl, request, context, permission):
    # It should only be possible for request.identity to be a User object
    # at this point, and we only a User in these policies.
    assert isinstance(request.identity, User)

    # Dispatch to our ACL
    # NOTE: These parameters are in a different order than the signature of this method.
    res = acl.permits(context, principals_for(request.identity), permission)

    # Verify email before you can manage account/projects.
    if (
        isinstance(res, Allowed)
        and not request.identity.has_primary_verified_email
        and request.matched_route.name.startswith("manage")
        and request.matched_route.name != "manage.account"
    ):
        return WarehouseDenied("unverified", reason="unverified_email")

    # If our underlying permits allowed this, we will check our 2FA status,
    # that might possibly return a reason to deny the request anyways, and if
    # it does we'll return that.
    if isinstance(res, Allowed):
        mfa = _check_for_mfa(request, context)
        if mfa is not None:
            return mfa

    return res


def _check_for_mfa(request, context) -> WarehouseDenied | None:
    # It should only be possible for request.identity to be a User object
    # at this point, and we only a User in these policies.
    assert isinstance(request.identity, User)

    # If we're in the manage namespace or file uploads, we'll check if the user
    # has 2FA enabled, and if they don't we'll deny them.

    # Management routes that don't require 2FA, mostly to set up 2FA.
    _exempt_routes = [
        "manage.account.recovery-codes",
        "manage.account.totp-provision",
        "manage.account.two-factor",
        "manage.account.webauthn-provision",
    ]

    if (
        request.matched_route.name.startswith("manage")
        and request.matched_route.name != "manage.account"
        and not any(
            request.matched_route.name.startswith(route) for route in _exempt_routes
        )
        and not request.identity.has_two_factor
    ):
        return WarehouseDenied(
            "You must enable two factor authentication to manage other settings",
            reason="manage_2fa_required",
        )

    if (
        request.matched_route.name == "forklift.legacy.file_upload"
        and not request.identity.has_two_factor
    ):
        return WarehouseDenied(
            "You must enable two factor authentication to upload",
            reason="upload_2fa_required",
        )

    return None
