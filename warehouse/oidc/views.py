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

from warehouse.admin.flags import AdminFlagValue
from warehouse.events.tags import EventTag
from warehouse.macaroons import caveats
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.oidc.interfaces import IOIDCProviderService
from warehouse.packaging.models import JournalEntry, Project, ProjectFactory, Role


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
        # NOTE: This is mostly a sanity check, since pending providers should
        # be disposed of as part of the ordinary project creation flow.
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

        # If the project doesn't exist, then we need to:
        # 1. Create it (with the pending provider's user as an owner);
        # 2. Reify the pending provider into a normal OIDC provider;
        # 3. Add the reified provider to the newly created project.

        # TODO: Dedupe this with `utils.project.add_project`?
        new_project = Project(name=pending_provider.project_name)
        request.db.add(new_project)

        request.db.add(
            JournalEntry(
                name=new_project.name,
                action="create",
                submitted_by=pending_provider.added_by,
                submitted_from=request.remote_addr,
            )
        )
        new_project.record_event(
            tag=EventTag.Project.ProjectCreate,
            ip_address=request.remote_addr,
            additional={"created_by": pending_provider.added_by.username},
        )

        request.db.add(
            Role(user=pending_provider.added_by, project=new_project, role_name="Owner")
        )

        # TODO: This should be handled by some sort of database trigger or a
        #       SQLAlchemy hook or the like instead of doing it inline in this
        #       view.
        request.db.add(
            JournalEntry(
                name=new_project.name,
                action=f"add Owner {pending_provider.added_by.username}",
                submitted_by=pending_provider.added_by,
                submitted_from=request.remote_addr,
            )
        )
        new_project.record_event(
            tag=EventTag.Project.RoleAdd,
            ip_address=request.remote_addr,
            additional={
                "submitted_by": pending_provider.added_by.username,
                "role_name": "Owner",
                "target_user": pending_provider.added_by.username,
            },
        )

        new_provider = pending_provider.reify()
        new_project.oidc_providers.append(new_provider)

        # From here, the pending OIDC provider is vestigial, so we can remove it.
        request.db.delete(pending_provider)
        request.db.flush()

    # We either don't have a pending OIDC provider, or we *did*
    # have one and we've just converted it. Either way, we look for a full
    # provider to actually do the macaroon minting with.
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
