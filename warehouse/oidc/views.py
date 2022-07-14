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

    try:
        body = request.json_body
    except ValueError:
        return _invalid(
            errors=[{"code": "invalid-json", "description": "missing JSON body"}]
        )

    unverified_jwt = body.get("token")
    if not unverified_jwt:
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
    now = time.time()
    expires = int(now) + 900
    projects = [p.normalized_name for p in provider.projects]
    caveats = [
        {"permissions": {"projects": projects}, "version": 1},
        {"nbf": int(now), "exp": expires},
    ]
    serialized, dm = macaroon_service.create_macaroon(
        location=request.domain,
        description=f"OpenID token: {provider} ({now})",
        caveats=caveats,
    )
    for project in provider.projects:
        project.record_event(
            tag="project:api_token:added",
            ip_address=request.remote_addr,
            additional={
                "description": dm.description,
                "expires": expires,
            },
        )
    return {"success": True, "token": serialized}
