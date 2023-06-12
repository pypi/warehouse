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

from pydantic import BaseModel, StrictStr, ValidationError
from pyramid.response import Response
from pyramid.view import view_config
from sqlalchemy import func

from warehouse.admin.flags import AdminFlagValue
from warehouse.email import send_pending_trusted_publisher_invalidated_email
from warehouse.events.tags import EventTag
from warehouse.macaroons import caveats
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.oidc.interfaces import IOIDCPublisherService
from warehouse.oidc.models import PendingOIDCPublisher
from warehouse.packaging.interfaces import IProjectService
from warehouse.packaging.models import ProjectFactory
from warehouse.rate_limiting.interfaces import IRateLimiter


class TokenPayload(BaseModel):
    token: StrictStr


def _ratelimiters(request):
    return {
        "user.oidc": request.find_service(
            IRateLimiter, name="user_oidc.publisher.register"
        ),
        "ip.oidc": request.find_service(
            IRateLimiter, name="ip_oidc.publisher.register"
        ),
    }


@view_config(
    route_name="oidc.audience",
    require_methods=["GET"],
    renderer="json",
    require_csrf=False,
    has_translations=False,
)
def oidc_audience(request):
    if request.flags.disallow_oidc():
        return Response(
            status=403, json={"message": "Trusted publishing functionality not enabled"}
        )

    audience = request.registry.settings["warehouse.oidc.audience"]
    return {"audience": audience}


@view_config(
    route_name="oidc.github.mint_token",
    require_methods=["POST"],
    renderer="json",
    require_csrf=False,
    has_translations=True,
)
def mint_token_from_oidc(request):
    def _invalid(errors):
        request.response.status = 422
        return {"message": "Token request failed", "errors": errors}

    if request.flags.disallow_oidc(AdminFlagValue.DISALLOW_GITHUB_OIDC):
        return _invalid(
            errors=[
                {
                    "code": "not-enabled",
                    "description": (
                        "GitHub-based trusted publishing functionality not enabled"
                    ),
                }
            ]
        )

    try:
        payload = TokenPayload.parse_raw(request.body)
        unverified_jwt = payload.token
    except ValidationError as exc:
        return _invalid(errors=[{"code": "invalid-payload", "description": str(exc)}])

    # For the time being, GitHub is our only OIDC publisher.
    # In the future, this should locate the correct service based on an
    # identifier in the request body.
    oidc_service = request.find_service(IOIDCPublisherService, name="github")
    claims = oidc_service.verify_jwt_signature(unverified_jwt)
    if not claims:
        return _invalid(
            errors=[
                {"code": "invalid-token", "description": "malformed or invalid token"}
            ]
        )

    # First, try to find a pending publisher.
    pending_publisher = oidc_service.find_publisher(claims, pending=True)
    if pending_publisher is not None:
        factory = ProjectFactory(request)

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
                ]
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

        # There might be other pending publishers for the same project name,
        # which we've now invalidated by creating the project. These would
        # be disposed of on use, but we explicitly dispose of them here while
        # also sending emails to their owners.
        stale_pending_publishers = (
            request.db.query(PendingOIDCPublisher)
            .filter(
                func.normalize_pep426_name(PendingOIDCPublisher.project_name)
                == func.normalize_pep426_name(pending_publisher.project_name)
            )
            .all()
        )
        for stale_publisher in stale_pending_publishers:
            send_pending_trusted_publisher_invalidated_email(
                request,
                stale_publisher.added_by,
                project_name=stale_publisher.project_name,
            )
            request.db.delete(stale_publisher)

    # We either don't have a pending OIDC publisher, or we *did*
    # have one and we've just converted it. Either way, look for a full publisher
    # to actually do the macaroon minting with.
    publisher = oidc_service.find_publisher(claims, pending=False)
    if not publisher:
        return _invalid(
            errors=[
                {
                    "code": "invalid-publisher",
                    "description": "valid token, but no corresponding publisher",
                }
            ]
        )

    # At this point, we've verified that the given JWT is valid for the given
    # project. All we need to do is mint a new token.
    # NOTE: For OIDC-minted API tokens, the Macaroon's description string
    # is purely an implementation detail and is not displayed to the user.
    macaroon_service = request.find_service(IMacaroonService, context=None)
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
            caveats.Expiration(expires_at=expires_at, not_before=not_before),
        ],
        oidc_publisher_id=publisher.id,
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
