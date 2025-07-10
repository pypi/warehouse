# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import http
import typing

from pyramid.httpexceptions import HTTPBadRequest
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
        raise TypeError("`permission` keyword is required")

    # Set defaults for API views
    kwargs.update(
        api_version="api-v0-danger",
        accept="application/vnd.pypi.api-v0-danger+json",
        openapi=True,
        renderer="json",
        require_csrf=False,
        # TODO: Can we apply a macaroon-based rate limiter here,
        #  and how might we set specific rate limits for user/project owners?
    )

    def _wrapper(wrapped):
        return view_config(**kwargs)(wrapped)

    return _wrapper


@api_v0_view_config(route_name="api.echo", permission=Permissions.APIEcho)
def api_echo(request: Request):
    return {
        "username": request.user.username,
    }


@api_v0_view_config(
    route_name="api.projects.observations",
    permission=Permissions.APIObservationsAdd,
    require_methods=["POST"],
)
def api_projects_observations(project: Project, request: Request) -> dict:
    data = request.json_body

    # We know that this is a valid observation kind, so we can use it directly
    kind = OBSERVATION_KIND_MAP[data["kind"]]

    # One case of needing more complex validation that OpenAPI does not yet support.
    # Here we express a dependency between fields, but the validity of the inspector_url
    # is handled by the OpenAPI schema.
    if kind == ObservationKind.IsMalware:
        if "inspector_url" not in data:
            raise HTTPBadRequest(
                json={
                    "error": "missing required fields",
                    "missing": ["inspector_url"],
                    "project": project.name,
                },
            )

    # Manually add an origin field to the observation for tracking
    data["origin"] = "api"

    project.record_observation(
        request=request,
        kind=kind,
        actor=request.user,
        summary=data["summary"],
        payload=data,
    )

    # Override the status code, instead returning Response which changes the renderer.
    request.response.status = http.HTTPStatus.ACCEPTED
    return {
        # TODO: What should we return to the caller?
        "project": project.name,
        "thanks": "for the observation",
    }
