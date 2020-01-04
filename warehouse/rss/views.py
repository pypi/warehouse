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

from datetime import timedelta

from pyramid.httpexceptions import HTTPBadRequest
from pyramid.view import view_config
from sqlalchemy.orm import joinedload

from warehouse.cache.origin import origin_cache
from warehouse.packaging.models import Project, Release
from warehouse.utils import now
from warehouse.xml import XML_CSP

DEFAULT_RESULTS = 40
MAX_RESULTS = 200


def _get_int_query_param(request, param, default=None):
    value = request.params.get(param)
    if not value:
        # Return default if 'param' is absent or has an empty value.
        return default
    try:
        return int(value)
    except ValueError:
        raise HTTPBadRequest(f"'{param}' must be an integer.") from None


@view_config(
    route_name="rss.updates",
    renderer="rss/updates.xml",
    decorator=[
        origin_cache(
            1 * 24 * 60 * 60,  # 1 day
            stale_while_revalidate=1 * 24 * 60 * 60,  # 1 day
            stale_if_error=5 * 24 * 60 * 60,  # 5 days
            keys=["all-projects"],
        )
    ],
)
def rss_updates(request):
    request.response.content_type = "text/xml"

    request.find_service(name="csp").merge(XML_CSP)

    latest_releases = (
        request.db.query(Release)
        .options(joinedload(Release.project))
        .order_by(Release.created.desc())
    )

    max_age = _get_int_query_param(request, "max_age")
    if max_age is not None:
        created_since = now() - timedelta(seconds=max_age)
        latest_releases = latest_releases.filter(Release.created > created_since)

    limit = min(_get_int_query_param(request, "limit", DEFAULT_RESULTS), MAX_RESULTS)
    latest_releases = latest_releases.limit(limit)

    return {"latest_releases": latest_releases.all()}


@view_config(
    route_name="rss.packages",
    renderer="rss/packages.xml",
    decorator=[
        origin_cache(
            1 * 24 * 60 * 60,  # 1 day
            stale_while_revalidate=1 * 24 * 60 * 60,  # 1 day
            stale_if_error=5 * 24 * 60 * 60,  # 5 days
            keys=["all-projects"],
        )
    ],
)
def rss_packages(request):
    request.response.content_type = "text/xml"

    request.find_service(name="csp").merge(XML_CSP)

    newest_projects = (
        request.db.query(Project)
        .options(joinedload(Project.releases, innerjoin=True))
        .order_by(Project.created.desc())
    )

    max_age = _get_int_query_param(request, "max_age")
    if max_age is not None:
        created_since = now() - timedelta(seconds=max_age)
        newest_projects = newest_projects.filter(Project.created > created_since)

    limit = min(_get_int_query_param(request, "limit", DEFAULT_RESULTS), MAX_RESULTS)
    newest_projects = newest_projects.limit(limit)

    return {"newest_projects": newest_projects.all()}
