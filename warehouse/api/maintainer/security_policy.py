# SPDX-License-Identifier: Apache-2.0
"""
Authenticate requests with Maintainer API keys.

Keys are bearer credentials as RFC 6750 defines them, read only from the
``Authorization`` header (section 2.1): never from a form body, which the
OAuth 2.1 draft discourages (section 5.1.2), or a query parameter, which it
forbids (section 5.1). Failures get the RFC 6750 section 3 error responses that
``bearer_challenge`` builds, which OAuth 2.1 section 5.3 repeats, with
RFC 9457 problem details bodies.

The one public submodule of ``warehouse.api.maintainer``: ``warehouse.accounts``
imports the policy, which imports ``warehouse.accounts`` back, so the package
can't re-export it without an import cycle.

See: https://www.rfc-editor.org/rfc/rfc6750
See: https://datatracker.ietf.org/doc/draft-ietf-oauth-v2-1/ (section 5)
See: https://www.rfc-editor.org/rfc/rfc9457
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NoReturn

from pyramid.httpexceptions import HTTPForbidden, HTTPUnauthorized
from pyramid.interfaces import ISecurityPolicy
from zope.interface import implementer

from warehouse.accounts.interfaces import IUserService
from warehouse.api.maintainer._authz import ACL, InsufficientScope, owner_holds_scope
from warehouse.api.maintainer._bearer import challenge, invalid_token
from warehouse.api.maintainer._context import ApiKeyContext
from warehouse.api.maintainer._errors import InvalidApiKeyError
from warehouse.api.maintainer._interfaces import IApiKeyService
from warehouse.api.maintainer._scopes import PERMISSION_SCOPES
from warehouse.api.maintainer._services import API_KEY_PREFIX
from warehouse.api.problems import problem
from warehouse.cache.http import add_vary_callback
from warehouse.errors import WarehouseDenied
from warehouse.predicates import auth_methods_for_route
from warehouse.utils.security_policy import (
    AuthenticationMethod,
    permission_allowed_by_authentication_method,
    principals_for,
)

if TYPE_CHECKING:
    from pyramid.httpexceptions import HTTPException
    from pyramid.request import Request
    from pyramid.security import Allowed, Denied

__all__ = ["ApiKeySecurityPolicy", "bearer_challenge"]


def _accepts_api_keys(request: Request) -> bool:
    """Whether the matched route opts in to API keys with auth_methods."""
    if not request.matched_route:
        return False
    allowed = auth_methods_for_route(request.matched_route)
    return allowed is not None and AuthenticationMethod.API_KEY in allowed


def _extract_api_key(request: Request) -> str | None:
    """Return the bearer credential if it carries the API key prefix."""
    authorization = request.headers.get("Authorization")
    if not authorization:
        return None

    auth_method, _, credential = authorization.partition(" ")
    credential = credential.strip()
    if auth_method.lower() != "bearer" or not credential.startswith(API_KEY_PREFIX):
        return None
    return credential


@implementer(ISecurityPolicy)
class ApiKeySecurityPolicy:
    def identity(self, request: Request) -> ApiKeyContext | None:
        if not _accepts_api_keys(request):
            return None

        request.add_response_callback(add_vary_callback("Authorization"))
        raw_key = _extract_api_key(request)
        if raw_key is None:
            return None

        request.authentication_method = AuthenticationMethod.API_KEY

        if request.banned.by_ip(request.remote_addr):
            return None

        api_key_service = request.find_service(IApiKeyService, context=None)
        try:
            api_key = api_key_service.verify(raw_key)
        except InvalidApiKeyError as exc:
            # Kept so the error response can say why without a second lookup.
            # Only the expiry time is specific to a key, and only a caller
            # holding that key can see it.
            request.api_key_rejection = str(exc)
            return None

        login_service = request.find_service(IUserService, context=None)
        is_disabled, _ = login_service.is_disabled(api_key.user_id)
        if is_disabled:
            return None

        return ApiKeyContext(user=api_key.user, api_key=api_key)

    def remember(
        self, request: Request, userid: str, **kw: object
    ) -> list[tuple[str, str]]:
        # API keys are sent on every request; there is nothing to remember.
        return []

    def forget(self, request: Request, **kw: object) -> list[tuple[str, str]]:
        return []

    def authenticated_userid(self, request: Request) -> NoReturn:
        # Handled by MultiSecurityPolicy
        raise NotImplementedError

    def permits(
        self, request: Request, context: object, permission: str
    ) -> Allowed | Denied:
        identity = request.identity
        assert isinstance(identity, ApiKeyContext)
        api_key = identity.api_key

        if not permission_allowed_by_authentication_method(
            permission, AuthenticationMethod.API_KEY
        ):
            return WarehouseDenied(
                f"Maintainer API keys are not valid for permission: {permission}!",
                reason="invalid_permission",
            )

        required_scope = PERMISSION_SCOPES.get(permission)
        if required_scope is None:
            return WarehouseDenied(
                f"No Maintainer API key scope grants permission: {permission}!",
                reason="invalid_permission",
            )
        if required_scope not in api_key.scopes:
            return InsufficientScope(
                f"Maintainer API key lacks the required scope: {required_scope}",
                scope=required_scope,
            )

        # Not insufficient_scope: the key has the scope, and a client told
        # to get one with it would loop. The account changed instead.
        if not owner_holds_scope(request, identity, required_scope):
            return WarehouseDenied(
                "Your account may no longer use Maintainer API key scope: "
                f"{required_scope}",
                reason="scope_not_permitted",
            )

        # The same account requirements the session policy enforces in
        # permits(); the banned-IP check is in identity().
        user = identity.user
        if not user.has_primary_verified_email:
            return WarehouseDenied(
                "Verify your primary email address to use Maintainer API keys.",
                reason="unverified_email",
            )
        if not user.has_two_factor:
            return WarehouseDenied(
                "You must enable two factor authentication.",
                reason="2fa_required",
            )

        result = ACL.permits(context, principals_for(identity), permission)
        if result and not identity.use_recorded:
            api_key_service = request.find_service(IApiKeyService, context=None)
            api_key_service.record_use(api_key.id)
            identity.use_recorded = True
        return result


def bearer_challenge(
    exc: HTTPException, request: Request
) -> HTTPUnauthorized | HTTPForbidden | None:
    """
    The RFC 6750 error response for an API request this policy turned away,
    or None to leave the response to the caller.

    See: https://www.rfc-editor.org/rfc/rfc6750#section-3.1
    """
    # Only permission denials; a predicate mismatch (wrong Accept, method) is
    # about the request's shape, not its credentials.
    if not isinstance(exc, HTTPForbidden) or not _accepts_api_keys(request):
        return None

    if isinstance(request.identity, ApiKeyContext):
        result = exc.result
        if isinstance(result, InsufficientScope):
            return problem(
                HTTPForbidden,
                result.msg,
                headers={
                    "WWW-Authenticate": challenge(
                        error="insufficient_scope",
                        error_description=result.msg,
                        scope=result.scope,
                    )
                },
            )
        # Any other denial, such as missing 2FA, says why; an ACL denial's
        # message names principals, so it stays generic. The bare challenge
        # is the one section 3 requires when the token doesn't enable access.
        return problem(
            HTTPForbidden,
            result.msg
            if isinstance(result, WarehouseDenied)
            else "Access was denied to this resource.",
            headers={"WWW-Authenticate": challenge()},
        )
    if request.identity is not None:
        return None

    # Malformed, unknown, revoked or expired.
    if (reason := getattr(request, "api_key_rejection", None)) is not None:
        return invalid_token(reason)
    return None
