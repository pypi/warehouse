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

from pyramid.view import view_config

from warehouse.admin.flags import AdminFlagValue
from warehouse.events.tags import EventTag
from warehouse.macaroons import caveats
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.oidc.interfaces import IOIDCProviderService


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
        body = request.json_body
    except ValueError:
        return _invalid(
            errors=[{"code": "invalid-json", "description": "missing JSON body"}]
        )

    unverified_jwt = body.get("token")
    if not unverified_jwt or not isinstance(unverified_jwt, str):
        return _invalid(
            errors=[{"code": "invalid-token", "description": "missing or empty token"}]
        )

    # For the time being, GitHub is our only OIDC provider.
    # In the future, this should locate the correct service based on an
    # identifier in the request body.
    oidc_service = request.find_service(IOIDCProviderService, name="github")
    provider = oidc_service.find_provider(unverified_jwt)
    if not provider:
        return _invalid(
            errors=[
                {"code": "invalid-token", "description": "malformed or invalid token"}
            ]
        )

    # At this point, we've verified that the given JWT is valid for the given
    # project. All we need to do is mint a new token.
    macaroon_service = request.find_service(IMacaroonService, context=None)
    not_before = int(time.time())
    expires_at = not_before + 900
    serialized, dm = macaroon_service.create_macaroon(
        request.domain,
        f"OpenID token: {provider} ({not_before})",
        [
            caveats.OIDCProvider(oidc_provider_id=str(provider.id)),
            caveats.ProjectID(project_ids=[str(p.id) for p in provider.projects]),
            caveats.Expiration(expires_at=expires_at, not_before=not_before),
        ],
        oidc_provider_id=provider.id,
    )
    for project in provider.projects:
        project.record_event(
            tag=EventTag.Project.APITokenAdded,
            ip_address=request.remote_addr,
            additional={
                "description": dm.description,
                "expires": expires_at,
            },
        )
    return {"success": True, "token": serialized}
