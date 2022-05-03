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


from pyramid.httpexceptions import HTTPMovedPermanently
from pyramid.view import view_config
from sqlalchemy import func

from warehouse.cache.http import cache_control
from warehouse.cache.origin import origin_cache
from warehouse.packaging.models import JournalEntry, Release


@view_config(
    route_name="legacy.api.draft.index",
    renderer="legacy/api/draft/index.html",
    decorator=[
        cache_control(10 * 60),  # 10 minutes
        origin_cache(
            1 * 24 * 60 * 60,  # 1 day
            stale_while_revalidate=5 * 60,  # 5 minutes
            stale_if_error=1 * 24 * 60 * 60,  # 1 day
        ),
    ],
)
def draft_index(draft_project_dict, request):
    # Get the latest serial number
    serial = request.db.query(func.max(JournalEntry.id)).scalar() or 0
    request.response.headers["X-PyPI-Last-Serial"] = str(serial)

    return {"draft_project_dict": draft_project_dict}


@view_config(
    route_name="legacy.api.draft.detail",
    context=Release,
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
def draft_detail(release, request):
    # Make sure that we're using the normalized version of the URL.
    if release.project.normalized_name != request.matchdict.get(
        "name", release.project.normalized_name
    ):
        return HTTPMovedPermanently(
            request.current_route_path(name=release.project.normalized_name)
        )

    # Get the latest serial number for this project.
    request.response.headers["X-PyPI-Last-Serial"] = str(release.project.last_serial)

    return {"project": release.project, "files": release.files.all()}
