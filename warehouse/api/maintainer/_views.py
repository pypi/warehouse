# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import datetime as dt
import time
import uuid

from typing import TYPE_CHECKING, Final, Literal, TypedDict

import jwt

from warehouse.api.echo import api_v0_view_config
from warehouse.api.maintainer._authz import owner_holds_scope
from warehouse.api.maintainer._bearer import invalid_token
from warehouse.api.maintainer._context import ApiKeyContext
from warehouse.api.maintainer._scopes import ApiKeyScope
from warehouse.authnz import Permissions

if TYPE_CHECKING:
    from pyramid.httpexceptions import HTTPUnauthorized
    from pyramid.request import Request

ACCESS_TOKEN_TTL: Final = dt.timedelta(minutes=15)
SCAFFOLD_AUDIENCE: Final = "urn:pypi:maintainer-api:unsigned-scaffold"

# TODO: These views use the danger-api decorator, Accept type and
#  /danger-api/ path for now. Once the Maintainer API has its own path and
#  media type, give these views their own view config here and drop the
#  dependency on warehouse.api.echo.


class AccessTokenClaims(TypedDict):
    """The scaffold's claim set. Not final; see ``api_token_exchange``."""

    iss: str
    aud: str
    sub: str
    iat: int
    exp: int
    jti: str
    api_key_id: str
    scp: str


class AccessTokenResponse(TypedDict):
    """An RFC 6749 section 5.1 access token response."""

    access_token: str
    token_type: Literal["Bearer"]
    expires_in: int


@api_v0_view_config(
    route_name="api.token.exchange",
    permission=Permissions.APIKeyExchange,
    require_methods=["POST"],
)
def api_token_exchange(request: Request) -> AccessTokenResponse | HTTPUnauthorized:
    """
    Trade the caller's Maintainer API key for a short-lived access token.

    Non-functional scaffolding. Issuing access tokens is left to a separate
    set of services, built later. Until then this returns a structurally
    valid JWT so clients can exercise the exchange, but it is unsigned
    (``alg: none``), its claim set is not final, and nothing accepts it.

    Before a signed version exists:

    - ``iss`` comes from the request's ``Host`` header; pin it to a
      configured value.
    - Follow the RFC 9068 access token profile, which this token doesn't: it
      must be signed, ``typ`` is ``JWT`` rather than ``at+jwt``, it has
      ``scp`` rather than ``scope`` and no ``client_id``, and ``aud`` names
      the scaffold.

    The response is shaped like RFC 6749 section 5.1's, served with the danger
    API media type rather than ``application/json``; the token is an RFC 7519
    JWT.

    See: https://www.rfc-editor.org/rfc/rfc6749#section-5.1
    See: https://www.rfc-editor.org/rfc/rfc7519
    See: https://www.rfc-editor.org/rfc/rfc9068
    """
    identity = request.identity
    assert isinstance(identity, ApiKeyContext)
    api_key = identity.api_key
    issued_at = int(time.time())
    # Never outlive the key that minted the token. expires is naive UTC.
    expires_at = min(
        issued_at + int(ACCESS_TOKEN_TTL.total_seconds()),
        int(api_key.expires.replace(tzinfo=dt.UTC).timestamp()),
    )
    # The key expired between authentication and now. Returned, not raised,
    # so the use already recorded is kept.
    if expires_at <= issued_at:
        return invalid_token("Maintainer API key expired.")
    claims: AccessTokenClaims = {
        "iss": request.host_url,
        # Marks the token as the unsigned scaffold, so nothing that later
        # accepts signed tokens for a real audience can mistake one for it.
        "aud": SCAFFOLD_AUDIENCE,
        "sub": str(api_key.user_id),
        "iat": issued_at,
        "exp": expires_at,
        "jti": str(uuid.uuid4()),
        "api_key_id": str(api_key.id),
        # Only scopes the owner still holds, space-delimited as in RFC 6749
        # section 3.3.
        "scp": " ".join(
            scope
            for scope in ApiKeyScope
            if scope in api_key.scopes and owner_holds_scope(request, identity, scope)
        ),
    }

    request.response.headers["Cache-Control"] = "no-store"
    request.response.headers["Pragma"] = "no-cache"
    return {
        # Unsigned on purpose: this is the scaffold described above.
        "access_token": jwt.encode(dict(claims), "", algorithm="none"),
        "token_type": "Bearer",
        "expires_in": expires_at - issued_at,
    }
