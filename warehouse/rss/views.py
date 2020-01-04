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
from sqlalchemy.orm import joinedload

from warehouse.accounts.models import User
from warehouse.cache.origin import origin_cache
from warehouse.packaging.models import Project, Release
from warehouse.xml import XML_CSP


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
        .limit(40)
        .all()
    )

    return {"latest_releases": latest_releases}


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
        .limit(40)
        .all()
    )

    return {"newest_projects": newest_projects}


@view_config(
    route_name="rss.user_updates",
    context=User,
    renderer="rss/user_updates.xml",
    decorator=[
        origin_cache(
            1 * 24 * 60 * 60,  # 1 day
            stale_while_revalidate=1 * 24 * 60 * 60,  # 1 day
            stale_if_error=5 * 24 * 60 * 60,  # 5 days
        )
    ],
)
def rss_user_updates(user, request):
    request.response.content_type = "text/xml"

    request.find_service(name="csp").merge(XML_CSP)

    latest_releases = (
        request.db.query(Release)
        .join(Project)
        .filter(Project.users.any(username=user.username))
        .options(joinedload(Release.project))
        .order_by(Release.created.desc())
        .limit(40)
        .all()
    )

    return {"latest_releases": latest_releases, "user": user}
