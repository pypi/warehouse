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

from pyramid.view import view_config

from warehouse.authnz import Permissions

if typing.TYPE_CHECKING:
    from pyramid.request import Request


# TODO: Move this to a more general-purpose API view helper module
def api_v1_view_config(**kwargs):
    """
    A helper decorator that is used to create a view configuration that is
    useful for API version 1 views. Usage:

        @api_v1_view_config(
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
        accept="application/vnd.pypi.api-v1+json",
        renderer="json",
        require_csrf=False,
        # TODO: Can we apply a macaroon-based rate limiter here,
        #  and how might we set specific rate limits for user/project owners?
    )

    def _wrapper(wrapped):
        return view_config(**kwargs)(wrapped)

    return _wrapper


@api_v1_view_config(
    route_name="api.echo",
    permission=Permissions.APIEcho,
)
def api_echo(request: Request):
    return {
        "username": request.user.username,
    }
