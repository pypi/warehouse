# SPDX-License-Identifier: Apache-2.0

from pyramid.httpexceptions import HTTPMovedPermanently
from pyramid.request import Request
from pyramid.view import view_config
from sqlalchemy import func

from warehouse.cache.http import add_vary, cache_control
from warehouse.cache.origin import origin_cache
from warehouse.packaging.models import JournalEntry, Project
from warehouse.packaging.utils import (
    _simple_detail,
    _simple_index,
    _valid_simple_detail_context,
)
from warehouse.utils.cors import _CORS_HEADERS

MIME_TEXT_HTML = "text/html"
MIME_PYPI_SIMPLE_V1_HTML = "application/vnd.pypi.simple.v1+html"
MIME_PYPI_SIMPLE_V1_JSON = "application/vnd.pypi.simple.v1+json"


def _select_content_type(request: Request) -> str:
    # The way this works, is this will return a list of
    # tuples of (mimetype, qvalue) that is acceptable for
    # our request, combining the request and the types
    # that we have passed in.
    #
    # When the request does not have an accept header, then
    # the full list of offers will be returned.
    #
    # When the request has accept headers, but none of them
    # match, it will be an empty list.
    offers = request.accept.acceptable_offers(
        [
            MIME_TEXT_HTML,
            MIME_PYPI_SIMPLE_V1_HTML,
            MIME_PYPI_SIMPLE_V1_JSON,
        ]
    )

    # Default case, we want to return whatever we want to return
    # by default when there is no Accept header.
    if not offers:
        return MIME_TEXT_HTML
    # We've selected a list of acceptable offers, so we'll take
    # the first one as our return type.
    else:
        return offers[0][0]


@view_config(
    route_name="api.simple.index",
    renderer="warehouse:templates/api/simple/index.html",
    decorator=[
        add_vary("Accept"),
        cache_control(10 * 60),  # 10 minutes
        origin_cache(
            1 * 24 * 60 * 60,  # 1 day
            stale_while_revalidate=5 * 60,  # 5 minutes
            stale_if_error=1 * 24 * 60 * 60,  # 1 day
        ),
    ],
)
def simple_index(request):
    # Determine what our content-type should be, and setup our request
    # to return the correct content types.
    request.response.content_type = _select_content_type(request)
    if request.response.content_type == MIME_PYPI_SIMPLE_V1_JSON:
        request.response.override_ttl = 30 * 60  # 30 minutes
        request.override_renderer = "json"

    # Apply CORS headers.
    request.response.headers.update(_CORS_HEADERS)

    # Get the latest serial number
    serial = request.db.query(func.max(JournalEntry.id)).scalar() or 0
    request.response.headers["X-PyPI-Last-Serial"] = str(serial)

    return _simple_index(request, serial)


@view_config(
    route_name="api.simple.detail",
    context=Project,
    renderer="warehouse:templates/api/simple/detail.html",
    decorator=[
        add_vary("Accept"),
        cache_control(10 * 60),  # 10 minutes
        origin_cache(
            1 * 24 * 60 * 60,  # 1 day
            stale_while_revalidate=5 * 60,  # 5 minutes
            stale_if_error=1 * 24 * 60 * 60,  # 1 day
        ),
    ],
)
def simple_detail(project, request):
    # Make sure that we're using the normalized version of the URL.
    if project.normalized_name != request.matchdict.get(
        "name", project.normalized_name
    ):
        return HTTPMovedPermanently(
            request.current_route_path(name=project.normalized_name),
            headers=_CORS_HEADERS,
        )

    # Determine what our content-type should be, and setup our request
    # to return the correct content types.
    request.response.content_type = _select_content_type(request)
    if request.response.content_type == MIME_PYPI_SIMPLE_V1_JSON:
        request.override_renderer = "json"

    # Apply CORS headers.
    request.response.headers.update(_CORS_HEADERS)

    # Get the latest serial number for this project.
    request.response.headers["X-PyPI-Last-Serial"] = str(project.last_serial)

    context = _simple_detail(project, request)

    # Modify the Jinja context to use valid variable name
    if request.response.content_type != MIME_PYPI_SIMPLE_V1_JSON:
        context = _valid_simple_detail_context(context)

    return context
