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

from datetime import date

from pyramid.view import view_config
from sqlalchemy import func

from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.oidc.interfaces import IOIDCProviderService
from warehouse.packaging.models import Project


@view_config(
    route_name="oidc.mint_token",
    require_methods=["POST"],
    renderer="json",
    require_csrf=False,
    has_translations=False,
)
def mint_token_from_oidc(request):
    def _invalid(msg):
        request.response.status = 422
        return {"error": msg}

    try:
        body = request.json_body
    except ValueError:
        return _invalid("missing body")

    unverified_jwt = body.get("token")
    if not unverified_jwt:
        return _invalid("missing token")

    project_name = body.get("project")
    if not project_name:
        return _invalid("missing project")

    project = (
        request.db.query(Project)
        .filter(Project.normalized_name == func.normalize_pep426_name(project_name))
        .one_or_none()
    )
    if not project:
        return _invalid(f"no such project: {project_name}")

    # For the time being, GitHub is our only OIDC provider.
    # In the future, this should locate the correct service based on an
    # identifier in the request body.
    oidc_service = request.find_service(IOIDCProviderService, name="github")
    if not oidc_service.verify_for_project(unverified_jwt, project):
        return _invalid(f"invalid token for project: {project_name}")

    # At this point, we've verified that the given JWT is valid for the given
    # project. All we need to do is mint a new token.
    macaroon_service = request.find_service(IMacaroonService, context=None)
    expires = int(time.time()) + 900
    caveats = [
        {"permissions": {"projects": [project.normalized_name]}, "version": 1},
        {"nbf": int(time.time()), "exp": expires},
    ]
    serialized, dm = macaroon_service.create_macaroon(
        location=request.domain,
        user_id=None,
        description="OpenID created ephemeral token",
        caveats=caveats,
    )
    project.record_event(
        tag="project:api_token:added",
        ip_address=request.remote_addr,
        additional={
            "description": dm.description,
            "expires": expires,
        },
    )
    return {"token": serialized}
