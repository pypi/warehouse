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


from pyramid.request import Request
from pyramid.httpexceptions import HTTPMovedPermanently
from pyramid.view import view_config
from sqlalchemy import func

from warehouse.cache.http import add_vary, cache_control
from warehouse.cache.origin import origin_cache
from warehouse.packaging.models import JournalEntry, Project
from warehouse.packaging.utils import _simple_detail


API_VERSION = "1.0"


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
            "text/html",
            "application/vnd.pypi.simple.v1+html",
            "application/vnd.pypi.simple.v1+json",
        ]
    )

    # Default case, we want to return whatevr we want to return
    # by default when there is no Accept header.
    if not offers:
        return "text/html"
    # We've selected a list of acceptable offers, so we'll take
    # the first one as our return type.
    else:
        return offers[0][0]


@view_config(
    route_name="legacy.api.simple.index",
    renderer="legacy/api/simple/index.html",
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
    if request.response.content_type == "application/vnd.pypi.simple.v1+json":
        request.override_renderer = "json"

    # Get the latest serial number
    serial = request.db.query(func.max(JournalEntry.id)).scalar() or 0
    request.response.headers["X-PyPI-Last-Serial"] = str(serial)

    # Fetch the name and normalized name for all of our projects
    projects = (
        request.db.query(Project.name, Project.normalized_name)
        .order_by(Project.normalized_name)
        .all()
    )

    return {
        "meta": {"api-version": API_VERSION, "_last-serial": serial},
        "projects": [{"name": p.name} for p in projects],
    }


@view_config(
    route_name="legacy.api.simple.detail",
    context=Project,
    renderer="legacy/api/simple/detail.html",
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
            request.current_route_path(name=project.normalized_name)
        )

    # Determine what our content-type should be, and setup our request
    # to return the correct content types.
    request.response.content_type = _select_content_type(request)
    if request.response.content_type == "application/vnd.pypi.simple.v1+json":
        request.override_renderer = "json"

    # Get the latest serial number for this project.
    request.response.headers["X-PyPI-Last-Serial"] = str(project.last_serial)

    # Get our simple data
    detail = _simple_detail(project, request)

    return {
        "meta": {"api-version": API_VERSION, "_last-serial": project.last_serial},
        "name": detail["project"].normalized_name,
        "files": [
            {
                "filename": file.filename,
                "url": request.route_url("packaging.file", path=file.path),
                "hashes": {
                    "sha256": file.sha256_digest,
                },
                "requires-python": file.release.requires_python,
                "yanked": file.release.yanked_reason
                if file.release.yanked and file.release.yanked.reason
                else file.release.yanked,
            }
            for file in detail["files"]
        ],
    }
