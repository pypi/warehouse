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
from __future__ import annotations

import typing

from pyramid.httpexceptions import HTTPAccepted, HTTPBadRequest
from pyramid.view import view_config

from warehouse.authnz import Permissions
from warehouse.observations.models import OBSERVATION_KIND_MAP, ObservationKind

if typing.TYPE_CHECKING:
    from pyramid.request import Request

    from warehouse.packaging.models import Project


# ### DANGER ZONE ### #
# These views are a v0, danger, all-bets-are-off version of the API.
# We may change the API at any time, and we may remove it entirely
# without notice, but we'll try to tell the folks we know are testing
# it before we do.


# TODO: Move this to a more general-purpose API view helper module
def api_v0_view_config(**kwargs):
    """
    A helper decorator that is used to create a view configuration that is
    useful for API version 0 views. Usage:

        @api_v0_view_config(
            route_name="api.projects",
            permission=Permissions.API...,
        )
        def ...
    """

    # Prevent developers forgetting to set a permission
    if "permission" not in kwargs:  # pragma: no cover (safety check)
        raise TypeError("`permission` keyword is is required")

    # Set defaults for API views
    kwargs.update(
        api_version="api-v0-danger",
        accept="application/vnd.pypi.api-v0-danger+json",
        renderer="json",
        require_csrf=False,
        # TODO: Can we apply a macaroon-based rate limiter here,
        #  and how might we set specific rate limits for user/project owners?
    )

    def _wrapper(wrapped):
        return view_config(**kwargs)(wrapped)

    return _wrapper


@api_v0_view_config(route_name="api.echo", permission=Permissions.APIEcho, openapi=True)
def api_echo(request: Request):
    return {
        "username": request.user.username,
    }


@api_v0_view_config(
    route_name="api.projects.observations",
    permission=Permissions.APIObservationsAdd,
    require_methods=["POST"],
)
def api_projects_observations(
    project: Project, request: Request
) -> HTTPAccepted | HTTPBadRequest:
    data = request.json_body

    # TODO: Are there better mechanisms for validating the payload?
    #  Maybe adopt https://github.com/Pylons/pyramid_openapi3 - too big?
    required_fields = {"kind", "summary"}
    if not required_fields.issubset(data.keys()):
        raise HTTPBadRequest(
            json={
                "error": "missing required fields",
                "missing": sorted(list(required_fields - data.keys())),
            },
        )
    try:
        # get the correct mapping for the `kind` field
        kind = OBSERVATION_KIND_MAP[data["kind"]]
    except KeyError:
        raise HTTPBadRequest(
            json={
                "error": "invalid kind",
                "kind": data["kind"],
                "project": project.name,
            }
        )

    # TODO: Another case of needing more complex validation
    if kind == ObservationKind.IsMalware:
        if "inspector_url" not in data:
            raise HTTPBadRequest(
                json={
                    "error": "missing required fields",
                    "missing": ["inspector_url"],
                    "project": project.name,
                },
            )
        if "inspector_url" in data and not data["inspector_url"].startswith(
            "https://inspector.pypi.io/"
        ):
            raise HTTPBadRequest(
                json={
                    "error": "invalid inspector_url",
                    "inspector_url": data["inspector_url"],
                    "project": project.name,
                },
            )

    project.record_observation(
        request=request,
        kind=kind,
        actor=request.user,
        summary=data["summary"],
        payload=data,
    )

    return HTTPAccepted(
        json={
            # TODO: What should we return to the caller?
            "project": project.name,
            "thanks": "for the observation",
        },
    )
