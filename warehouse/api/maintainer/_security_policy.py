# SPDX-License-Identifier: Apache-2.0

from pyramid.authorization import ACLHelper
from pyramid.httpexceptions import HTTPUnauthorized
from pyramid.interfaces import ISecurityPolicy
from zope.interface import implementer

from warehouse.accounts.interfaces import IUserService
from warehouse.api.maintainer._errors import ExpiredApiKeyError, InvalidApiKeyError
from warehouse.api.maintainer._interfaces import IApiKeyService
from warehouse.api.maintainer._models import ApiKeyScope
from warehouse.api.maintainer._services import API_KEY_PREFIX
from warehouse.api.maintainer._utils import ApiKeyContext
from warehouse.authnz import Permissions
from warehouse.cache.http import add_vary_callback
from warehouse.errors import WarehouseDenied
from warehouse.predicates import auth_methods_for_route
from warehouse.utils.security_policy import (
    AuthenticationMethod,
    permission_allowed_by_authentication_method,
    principals_for,
)

# The scope a key must carry for each permission it may exercise. A permission
# that API_KEY may grant but that is missing here is denied.
PERMISSION_SCOPES: dict[Permissions, ApiKeyScope] = {
    Permissions.ProjectsYank: ApiKeyScope.ProjectReleasesYank,
}


def _extract_api_key(request) -> str | None:
    """Return the bearer credential if it carries the API key prefix."""
    authorization = request.headers.get("Authorization")
    if not authorization:
        return None

    auth_method, _, credential = authorization.partition(" ")
    if auth_method.lower() != "bearer" or not credential.startswith(API_KEY_PREFIX):
        return None
    return credential


@implementer(ISecurityPolicy)
class ApiKeySecurityPolicy:
    def __init__(self):
        self._acl = ACLHelper()

    def identity(self, request):
        request.add_response_callback(add_vary_callback("Authorization"))
        request.authentication_method = AuthenticationMethod.API_KEY

        # Only routes that opt in with auth_methods accept API keys.
        if not request.matched_route:
            return None
        allowed = auth_methods_for_route(request.matched_route)
        if allowed is None or AuthenticationMethod.API_KEY not in allowed:
            return None

        raw_key = _extract_api_key(request)
        if raw_key is None:
            return None

        api_key_service = request.find_service(IApiKeyService, context=None)
        try:
            api_key = api_key_service.verify(raw_key)
        except ExpiredApiKeyError as exc:
            # Only a caller holding the full key gets here, so saying why leaks
            # nothing, and matches the "token is expired" macaroon denial.
            raise HTTPUnauthorized(
                headers={
                    "WWW-Authenticate": (
                        f'Bearer error="invalid_token", error_description="{exc}"'
                    )
                },
            )
        except InvalidApiKeyError:
            return None

        login_service = request.find_service(IUserService, context=None)
        is_disabled, _ = login_service.is_disabled(api_key.user_id)
        if is_disabled:
            return None

        api_key_service.record_use(api_key.id)
        return ApiKeyContext(user=api_key.user, api_key=api_key)

    def remember(self, request, userid, **kw):
        # API keys are sent on every request; there is nothing to remember.
        return []

    def forget(self, request, **kw):
        return []

    def authenticated_userid(self, request):
        # Handled by MultiSecurityPolicy
        raise NotImplementedError

    def permits(self, request, context, permission):
        assert isinstance(request.identity, ApiKeyContext)

        if not permission_allowed_by_authentication_method(
            permission, AuthenticationMethod.API_KEY
        ):
            return WarehouseDenied(
                f"API keys are not valid for permission: {permission}!",
                reason="invalid_permission",
            )

        required_scope = PERMISSION_SCOPES.get(permission)
        if required_scope is None:
            return WarehouseDenied(
                f"No API key scope grants permission: {permission}!",
                reason="invalid_permission",
            )
        if required_scope not in request.identity.api_key.scopes:
            return WarehouseDenied(
                f"API key lacks the required scope: {required_scope}",
                reason="insufficient_scope",
            )

        # The same account requirements the session policy enforces.
        user = request.identity.user
        if not user.has_primary_verified_email:
            return WarehouseDenied("unverified", reason="unverified_email")
        if not user.has_two_factor:
            return WarehouseDenied(
                "You must enable two factor authentication.",
                reason="2fa_required",
            )

        # NOTE: These parameters are in a different order than the signature of this
        #       method.
        return self._acl.permits(context, principals_for(request.identity), permission)
