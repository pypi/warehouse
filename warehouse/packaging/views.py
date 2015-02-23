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

from pyramid.httpexceptions import HTTPMovedPermanently, HTTPNotFound
from pyramid.view import view_config
from sqlalchemy.orm.exc import NoResultFound

from warehouse.accounts.models import User
from warehouse.cache.http import cache_control, surrogate_control
from warehouse.packaging.interfaces import IDownloadStatService
from warehouse.packaging.models import Release, Role


@view_config(
    route_name="packaging.project",
    renderer="packaging/detail.html",
    decorator=[
        cache_control(1 * 24 * 60 * 60),      # 1 day
        surrogate_control(7 * 24 * 60 * 60),  # 7 days
    ],
    mapper="pyramid.config.views:DefaultViewMapper",
)
def project_detail(project, request):
    if project.name != request.matchdict.get("name", project.name):
        return HTTPMovedPermanently(
            request.current_route_url(name=project.name),
        )

    try:
        release = project.releases.order_by(
            Release._pypi_ordering.desc()
        ).limit(1).one()
    except NoResultFound:
        raise HTTPNotFound from None

    return release_detail(release, request)


@view_config(
    route_name="packaging.release",
    renderer="packaging/detail.html",
    decorator=[
        cache_control(7 * 24 * 60 * 60),       # 7 days
        surrogate_control(30 * 24 * 60 * 60),  # 30 days
    ],
    mapper="pyramid.config.views:DefaultViewMapper",
)
def release_detail(release, request):
    project = release.project

    if project.name != request.matchdict.get("name", project.name):
        return HTTPMovedPermanently(
            request.current_route_url(name=project.name),
        )

    # Get all of the registered versions for this Project, in order of newest
    # to oldest.
    all_releases = (
        project.releases
        .with_entities(Release.version, Release.created)
        .order_by(Release._pypi_ordering.desc())
        .all()
    )

    # Get all of the maintainers for this project.
    maintainers = [
        r.user
        for r in (
            request.db.query(Role)
            .join(User)
            .filter(Role.project == project)
            .distinct(User.username)
            .order_by(User.username)
            .all()
        )
    ]

    stats_svc = request.find_service(IDownloadStatService)

    return {
        "project": project,
        "release": release,
        "all_releases": all_releases,
        "maintainers": maintainers,
        "download_stats": {
            "daily": stats_svc.get_daily_stats(project.name),
            "weekly": stats_svc.get_weekly_stats(project.name),
            "monthly": stats_svc.get_monthly_stats(project.name),
        },
    }
