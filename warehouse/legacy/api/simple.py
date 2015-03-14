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

from pyramid.view import view_config
from sqlalchemy import func

from warehouse.cache.http import cache_control
from warehouse.cache.origin import origin_cache
from warehouse.packaging.models import JournalEntry, Project


@view_config(
    route_name="legacy.api.simple.index",
    renderer="legacy/api/simple/index.html",
    decorator=[
        cache_control(10 * 60),  # 10 minutes
        origin_cache(7 * 24 * 60 * 60),   # 7 days
    ],
)
def simple_index(request):
    # Get the latest serial number
    serial = request.db.query(func.max(JournalEntry.id)).scalar() or 0
    request.response.headers["X-PyPI-Last-Serial"] = serial

    # Fetch the name and normalized name for all of our projects
    projects = (
        request.db.query(Project.name, Project.normalized_name)
                  .order_by(Project.normalized_name)
                  .all()
    )

    return {"projects": projects}
