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


from packaging.version import parse
from pyramid.httpexceptions import HTTPMovedPermanently
from pyramid.view import view_config
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from warehouse.cache.http import cache_control
from warehouse.cache.origin import origin_cache
from warehouse.packaging.models import File, JournalEntry, Project, Release


@view_config(
    route_name="legacy.api.simple.index",
    renderer="legacy/api/simple/index.html",
    decorator=[
        cache_control(10 * 60),  # 10 minutes
        origin_cache(
            1 * 24 * 60 * 60,  # 1 day
            stale_while_revalidate=5 * 60,  # 5 minutes
            stale_if_error=1 * 24 * 60 * 60,  # 1 day
        ),
    ],
)
def simple_index(request):
    # Get the latest serial number
    serial = request.db.query(func.max(JournalEntry.id)).scalar() or 0
    request.response.headers["X-PyPI-Last-Serial"] = str(serial)

    # Fetch the name and normalized name for all of our projects
    projects = (
        request.db.query(Project.name, Project.normalized_name)
        .order_by(Project.normalized_name)
        .all()
    )

    return {"projects": projects}


def _simple_detail(project, request):
    # Get all of the files for this project.
    files = sorted(
        request.db.query(File)
        .options(joinedload(File.release))
        .join(Release)
        .filter(Release.project == project)
        .all(),
        key=lambda f: (parse(f.release.version), f.filename),
    )

    return {"project": project, "files": files}


@view_config(
    route_name="legacy.api.simple.detail",
    context=Project,
    renderer="legacy/api/simple/detail.html",
    decorator=[
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

    # Get the latest serial number for this project.
    request.response.headers["X-PyPI-Last-Serial"] = str(project.last_serial)

    return _simple_detail(project, request)
