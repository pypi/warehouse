# SPDX-License-Identifier: Apache-2.0

"""
Configuration for the warehouse API
"""

from __future__ import annotations

import typing

from pathlib import Path

import orjson

from warehouse.config import Environment

if typing.TYPE_CHECKING:
    from pyramid.config import Configurator


def _api_set_content_type(view, info):
    """
    Set the content type based on API version parameter.

    Use in a `@view_config` decorator like so:

        @view_config(renderer="json", api_version="v1", ...)
        def my_view(request):
            return {"hello": "world"}

    This will set the content type to `application/vnd.pypi.v1+json` and
    pass to whatever `json` renderer is configured.
    """
    if api_version := info.options.get("api_version"):  # pragma: no cover

        def wrapper(context, request):
            request.response.content_type = f"application/vnd.pypi.{api_version}+json"
            return view(context, request)

        return wrapper
    return view


_api_set_content_type.options = ("api_version",)  # type: ignore[attr-defined]


def includeme(config: Configurator) -> None:
    config.add_view_deriver(_api_set_content_type)

    # Set up OpenAPI
    config.include("pyramid_openapi3")
    config.pyramid_openapi3_spec(
        str(Path(__file__).parent / "openapi.yaml"),
        route="/api/openapi.yaml",
    )
    # We use vendor prefixes to indicate the API version, so we need to add
    # deserializers for each version.
    config.pyramid_openapi3_add_deserializer(
        "application/vnd.pypi.api-v0-danger+json", orjson.loads
    )
    if config.registry.settings["warehouse.env"] == Environment.development:
        # Set up the route for the OpenAPI Web UI
        config.pyramid_openapi3_add_explorer(route="/api/explorer/")

    # Helpful toggles for development.
    # config.registry.settings["pyramid_openapi3.enable_endpoint_validation"] = False
    # config.registry.settings["pyramid_openapi3.enable_request_validation"] = False
    # config.registry.settings["pyramid_openapi3.enable_response_validation"] = False
