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

from pydantic import BaseModel, StrictStr, ValidationError
from pyramid.view import view_config
from sqlalchemy import func

from warehouse.admin.flags import AdminFlagValue
from warehouse.email import send_pending_oidc_provider_invalidated_email
from warehouse.events.tags import EventTag
from warehouse.macaroons import caveats
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.oidc.interfaces import IOIDCProviderService
from warehouse.oidc.models import PendingOIDCProvider
from warehouse.packaging.interfaces import IProjectService
from warehouse.packaging.models import ProjectFactory


class TokenPayload(BaseModel):
    token: StrictStr


@view_config(
    route_name="oidc.mint_token",
    require_methods=["POST"],
    renderer="json",
    require_csrf=False,
    has_translations=False,
)
def mint_token_from_oidc(request):
    def _invalid(errors):
        request.response.status = 422
        return {"message": "Token request failed", "errors": errors}

    oidc_enabled = request.registry.settings[
        "warehouse.oidc.enabled"
    ] and not request.flags.enabled(AdminFlagValue.DISALLOW_OIDC)
    if not oidc_enabled:
        return _invalid(
            errors=[
                {
                    "code": "not-enabled",
                    "description": "OIDC functionality not enabled",
                }
            ]
        )

    try:
        payload = TokenPayload.parse_raw(request.body)
        unverified_jwt = payload.token
    except ValidationError as exc:
        return _invalid(errors=[{"code": "invalid-payload", "description": str(exc)}])

    # For the time being, GitHub is our only OIDC provider.
    # In the future, this should locate the correct service based on an
    # identifier in the request body.
    oidc_service = request.find_service(IOIDCProviderService, name="github")
    claims = oidc_service.verify_jwt_signature(unverified_jwt)
    if not claims:
        return _invalid(
            errors=[
                {"code": "invalid-token", "description": "malformed or invalid token"}
            ]
        )

    # First, try to find a pending provider.
    pending_provider = oidc_service.find_provider(claims, pending=True)
    if pending_provider is not None:
        factory = ProjectFactory(request)

        # If the project already exists, this pending provider is no longer
        # valid and needs to be removed.
        # NOTE: This is mostly a sanity check, since we dispose of invalidated
        # pending providers below.
        if pending_provider.project_name in factory:
            request.db.delete(pending_provider)
            return _invalid(
                errors=[
                    {
                        "code": "invalid-pending-provider",
                        "description": "valid token, but project already exists",
                    }
                ]
            )

        # Create the new project, and reify the pending provider against it.
        project_service = request.find_service(IProjectService)
        new_project = project_service.create_project(
            pending_provider.project_name, pending_provider.added_by
        )
        oidc_service.reify_pending_provider(pending_provider, new_project)

        # There might be other pending providers for the same project name,
        # which we've now invalidated by creating the project. These would
        # be disposed of on use, but we explicitly dispose of them here while
        # also sending emails to their owners.
        stale_pending_providers = (
            request.db.query(PendingOIDCProvider)
            .filter(
                func.normalize_pep426_name(PendingOIDCProvider.project_name)
                == func.normalize_pep426_name(pending_provider.project_name)
            )
            .all()
        )
        for stale_provider in stale_pending_providers:
            send_pending_oidc_provider_invalidated_email(
                request,
                stale_provider.added_by,
                project_name=stale_provider.project_name,
            )
            request.db.delete(stale_provider)

    # We either don't have a pending OIDC provider, or we *did*
    # have one and we've just converted it. Either way, look for a full provider
    # to actually do the macaroon minting with.
    provider = oidc_service.find_provider(claims, pending=False)
    if not provider:
        return _invalid(
            errors=[
                {
                    "code": "invalid-provider",
                    "description": "valid token, but no corresponding provider",
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
        f"OpenID token: {provider.provider_url} ({not_before})",
        [
            caveats.OIDCProvider(oidc_provider_id=str(provider.id)),
            caveats.ProjectID(project_ids=[str(p.id) for p in provider.projects]),
            caveats.Expiration(expires_at=expires_at, not_before=not_before),
        ],
        oidc_provider_id=provider.id,
    )
    for project in provider.projects:
        project.record_event(
            tag=EventTag.Project.ShortLivedAPITokenAdded,
            ip_address=request.remote_addr,
            additional={
                "expires": expires_at,
                "provider_name": provider.provider_name,
                "provider_url": provider.provider_url,
            },
        )
    return {"success": True, "token": serialized}
