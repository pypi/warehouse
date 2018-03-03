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

from first import first
from pyramid.httpexceptions import HTTPMovedPermanently, HTTPNotFound
from pyramid.view import view_config
from sqlalchemy.orm.exc import NoResultFound

from warehouse.accounts.models import User
from warehouse.cache.origin import origin_cache
from warehouse.packaging.models import Release, Role


@view_config(
    route_name="packaging.project",
    renderer="packaging/detail.html",
    decorator=[
        origin_cache(
            1 * 24 * 60 * 60,                         # 1 day
            stale_while_revalidate=1 * 24 * 60 * 60,  # 1 day
            stale_if_error=5 * 24 * 60 * 60,          # 5 days
        ),
    ],
)
def project_detail(project, request):
    if project.name != request.matchdict.get("name", project.name):
        return HTTPMovedPermanently(
            request.current_route_path(name=project.name),
        )

    try:
        release = (
            request.db.query(Release)
                      .filter(Release.project == project)
                      .order_by(
                          Release.is_prerelease.nullslast(),
                          Release._pypi_ordering.desc())
                      .limit(1)
                      .one()
        )
    except NoResultFound:
        return HTTPNotFound()

    return release_detail(release, request)


@view_config(
    route_name="packaging.release",
    renderer="packaging/detail.html",
    decorator=[
        origin_cache(
            1 * 24 * 60 * 60,                         # 1 day
            stale_while_revalidate=1 * 24 * 60 * 60,  # 1 day
            stale_if_error=5 * 24 * 60 * 60,          # 5 days
        ),
    ],
)
def release_detail(release, request):
    project = release.project

    if not {project.name, release.version} <= set(request.matchdict.values()):
        return HTTPMovedPermanently(
            request.current_route_path(
                name=project.name, version=release.version,
            ),
        )

    # Get all of the registered versions for this Project, in order of newest
    # to oldest.
    all_releases = (
        request.db.query(Release)
                  .filter(Release.project == project)
                  .with_entities(
                      Release.version,
                      Release.is_prerelease,
                      Release.created)
                  .order_by(Release._pypi_ordering.desc())
                  .all()
    )

    # Get the latest non-prerelease of this Project, or the latest release if
    # all releases are prereleases.
    latest_release = first(
        all_releases,
        key=lambda r: not r.is_prerelease,
        default=all_releases[0],
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

    # Get the license from the classifiers or metadata, preferring classifiers.
    license = None
    if release.license:
        # Make a best effort when the entire license text is given
        # by using the first line only.
        license = release.license.split('\n')[0]
    license_classifiers = [c.split(" :: ")[-1] for c in release.classifiers
                           if c.startswith("License")]
    if license_classifiers:
        license = ', '.join(license_classifiers)

    return {
        "project": project,
        "release": release,
        "files": release.files.all(),
        "latest_release": latest_release,
        "all_releases": all_releases,
        "maintainers": maintainers,
        "license": license,
    }


@view_config(
    route_name="includes.edit-project-button",
    renderer="includes/edit-project-button.html",
    uses_session=True,
    permission="manage",
)
def edit_project_button(project, request):
    return {'project': project}
