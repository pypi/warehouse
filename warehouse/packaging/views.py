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
from sqlalchemy import func as sql_func
from sqlalchemy.orm.exc import NoResultFound

from warehouse.accounts.models import User
from warehouse.packaging.interfaces import IDownloadStatService
from warehouse.packaging.models import Project, Release, Role
from warehouse.utils.http import cache_control, surrogate_control


@view_config(
    route_name="packaging.project",
    renderer="packaging/detail.html",
    decorator=[
        cache_control(1 * 24 * 60 * 60),      # 1 day
        surrogate_control(7 * 24 * 60 * 60),  # 7 days
    ],
)
@view_config(
    route_name="packaging.release",
    renderer="packaging/detail.html",
    decorator=[
        cache_control(7 * 24 * 60 * 60),       # 7 days
        surrogate_control(30 * 24 * 60 * 60),  # 30 days
    ],
)
def project_detail(request, *, name, version=None):
    try:
        project = request.db.query(Project).filter(
            Project.normalized_name == sql_func.lower(
                sql_func.regexp_replace(name, "_", "-", "ig")
            )
        ).one()
    except NoResultFound:
        raise HTTPNotFound

    if project.name != name:
        # We've found the project but the project name isn't quite right so
        # we'll redirect them to the correct one.
        return HTTPMovedPermanently(
            request.current_route_url(name=project.name),
        )

    try:
        if version is None:
            # If there's no version specified, then we use the latest version
            release = project.releases.order_by(
                Release._pypi_ordering.desc()
            ).limit(1).one()
        else:
            release = project.releases.filter(Release.version == version).one()
    except NoResultFound:
        raise HTTPNotFound

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
