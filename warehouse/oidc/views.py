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

import time

from datetime import datetime
from typing import TypedDict

import jwt
import sentry_sdk

from pydantic import BaseModel, StrictStr, ValidationError
from pyramid.request import Request
from pyramid.response import Response
from pyramid.view import view_config

from warehouse.events.tags import EventTag
from warehouse.macaroons import caveats
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.macaroons.services import DatabaseMacaroonService
from warehouse.metrics.interfaces import IMetricsService
from warehouse.oidc.errors import InvalidPublisherError
from warehouse.oidc.interfaces import IOIDCPublisherService
from warehouse.oidc.models import OIDCPublisher, PendingOIDCPublisher
from warehouse.oidc.services import OIDCPublisherService
from warehouse.oidc.utils import OIDC_ISSUER_ADMIN_FLAGS, OIDC_ISSUER_SERVICE_NAMES
from warehouse.packaging.interfaces import IProjectService
from warehouse.packaging.models import ProjectFactory
from warehouse.rate_limiting.interfaces import IRateLimiter


class Error(TypedDict):
    code: str
    description: str


class JsonResponse(TypedDict, total=False):
    message: str | None
    errors: list[Error] | None
    token: StrictStr | None
    success: bool | None


class TokenPayload(BaseModel):
    token: StrictStr


def _ratelimiters(request: Request) -> dict[str, IRateLimiter]:
    return {
        "user.oidc": request.find_service(
            IRateLimiter, name="user_oidc.publisher.register"
        ),
        "ip.oidc": request.find_service(
            IRateLimiter, name="ip_oidc.publisher.register"
        ),
    }


def _invalid(errors: list[Error], request: Request) -> JsonResponse:
    request.response.status = 422

    return {
        "message": "Token request failed",
        "errors": errors,
    }


@view_config(
    route_name="oidc.audience",
    require_methods=["GET"],
    renderer="json",
    require_csrf=False,
    has_translations=False,
)
def oidc_audience(request: Request):
    if request.flags.disallow_oidc():
        return Response(
            status=403, json={"message": "Trusted publishing functionality not enabled"}
        )

    audience: str = request.registry.settings["warehouse.oidc.audience"]
    return {"audience": audience}


@view_config(
    route_name="oidc.github.mint_token",
    require_methods=["POST"],
    renderer="json",
    require_csrf=False,
)
@view_config(
    route_name="oidc.mint_token",
    require_methods=["POST"],
    renderer="json",
    require_csrf=False,
)
def mint_token_from_oidc(request: Request):
    try:
        payload = TokenPayload.model_validate_json(request.body)
        unverified_jwt = payload.token
    except ValidationError as exc:
        return _invalid(
            errors=[{"code": "invalid-payload", "description": str(exc)}],
            request=request,
        )

    # We currently have an **unverified** JWT. To verify it, we need to
    # know which OIDC service's keyring to check it against.
    # To do this, we gingerly peek into the unverified claims and
    # use the `iss` to key into the right `OIDCPublisherService`.
    try:
        unverified_claims = jwt.decode(
            unverified_jwt, options=dict(verify_signature=False)
        )
        unverified_issuer: str = unverified_claims["iss"]
    except Exception as e:
        metrics = request.find_service(IMetricsService, context=None)
        metrics.increment("warehouse.oidc.mint_token_from_oidc.malformed_jwt")

        # We expect only PyJWTError and KeyError; anything else indicates
        # an abstraction leak in jwt that we'll log for upstream reporting.
        if not isinstance(e, (jwt.PyJWTError, KeyError)):
            with sentry_sdk.push_scope() as scope:
                scope.fingerprint = e
                sentry_sdk.capture_message(f"jwt.decode raised generic error: {e}")

        return _invalid(
            errors=[{"code": "invalid-payload", "description": "malformed JWT"}],
            request=request,
        )

    # Associate the given issuer claim with Warehouse's OIDCPublisherService.
    service_name = OIDC_ISSUER_SERVICE_NAMES.get(unverified_issuer)
    if not service_name:
        return _invalid(
            errors=[
                {
                    "code": "invalid-payload",
                    "description": "unknown trusted publishing issuer",
                }
            ],
            request=request,
        )

    if request.flags.disallow_oidc(OIDC_ISSUER_ADMIN_FLAGS[unverified_issuer]):
        return _invalid(
            errors=[
                {
                    "code": "not-enabled",
                    "description": f"{service_name} trusted publishing functionality not enabled",  # noqa
                }
            ],
            request=request,
        )

    oidc_service: OIDCPublisherService = request.find_service(
        IOIDCPublisherService, name=service_name
    )

    return mint_token(oidc_service, unverified_jwt, request)


def mint_token(
    oidc_service: OIDCPublisherService, unverified_jwt: str, request: Request
) -> JsonResponse:
    claims = oidc_service.verify_jwt_signature(unverified_jwt)
    if not claims:
        return _invalid(
            errors=[
                {"code": "invalid-token", "description": "malformed or invalid token"}
            ],
            request=request,
        )

    # First, try to find a pending publisher.
    try:
        pending_publisher = oidc_service.find_publisher(claims, pending=True)
        factory = ProjectFactory(request)

        if isinstance(pending_publisher, PendingOIDCPublisher):
            # If the project already exists, this pending publisher is no longer
            # valid and needs to be removed.
            # NOTE: This is mostly a sanity check, since we dispose of invalidated
            # pending publishers below.
            if pending_publisher.project_name in factory:
                request.db.delete(pending_publisher)
                return _invalid(
                    errors=[
                        {
                            "code": "invalid-pending-publisher",
                            "description": "valid token, but project already exists",
                        }
                    ],
                    request=request,
                )

            # Create the new project, and reify the pending publisher against it.
            project_service = request.find_service(IProjectService)
            new_project = project_service.create_project(
                pending_publisher.project_name,
                pending_publisher.added_by,
                request,
                ratelimited=False,
            )

            oidc_service.reify_pending_publisher(pending_publisher, new_project)

            # Successfully converting a pending publisher into a normal publisher
            # is a positive signal, so we reset the associated ratelimits.
            ratelimiters = _ratelimiters(request)
            ratelimiters["user.oidc"].clear(pending_publisher.added_by.id)
            ratelimiters["ip.oidc"].clear(request.remote_addr)
    except InvalidPublisherError:
        # If the claim set isn't valid for a pending publisher, it's OK, we
        # will try finding a regular publisher
        pass

    # We either don't have a pending OIDC publisher, or we *did*
    # have one and we've just converted it. Either way, look for a full publisher
    # to actually do the macaroon minting with.
    try:
        publisher = oidc_service.find_publisher(claims, pending=False)
        # NOTE: assert to persuade mypy of the correct type here.
        assert isinstance(publisher, OIDCPublisher)
    except InvalidPublisherError as e:
        return _invalid(
            errors=[
                {
                    "code": "invalid-publisher",
                    "description": f"valid token, but no corresponding publisher ({e})",
                }
            ],
            request=request,
        )

    # At this point, we've verified that the given JWT is valid for the given
    # project. All we need to do is mint a new token.
    # NOTE: For OIDC-minted API tokens, the Macaroon's description string
    # is purely an implementation detail and is not displayed to the user.
    macaroon_service: DatabaseMacaroonService = request.find_service(
        IMacaroonService, context=None
    )
    not_before = int(time.time())
    expires_at = not_before + 900
    serialized, dm = macaroon_service.create_macaroon(
        request.domain,
        (
            f"OpenID token: {str(publisher)} "
            f"({datetime.fromtimestamp(not_before).isoformat()})"
        ),
        [
            caveats.OIDCPublisher(
                oidc_publisher_id=str(publisher.id),
            ),
            caveats.ProjectID(project_ids=[str(p.id) for p in publisher.projects]),
            # TODO: Use an enum from warehouse.authz.Permission
            caveats.Permission(permissions=["upload"]),
            caveats.Expiration(expires_at=expires_at, not_before=not_before),
        ],
        oidc_publisher_id=str(publisher.id),
        additional={"oidc": {"ref": claims.get("ref"), "sha": claims.get("sha")}},
    )
    for project in publisher.projects:
        project.record_event(
            tag=EventTag.Project.ShortLivedAPITokenAdded,
            request=request,
            additional={
                "expires": expires_at,
                "publisher_name": publisher.publisher_name,
                "publisher_url": publisher.publisher_url(),
            },
        )
    return {"success": True, "token": serialized}
