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

from warehouse.utils import readme
from warehouse.accounts.models import User
from warehouse.cache.origin import origin_cache
from warehouse.packaging.models import Project, Release, Role


@view_config(
    route_name="packaging.project",
    context=Project,
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
    context=Release,
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

    # Check if the requested version is equivalent but not exactly the same as
    # the release's version. Use `.get` because this view is used by
    # `project_detail` and there may not be a version.
    #
    # This also handles the case where both the version and the project name
    # need adjusted, and handles it in a single redirect.
    if release.version != request.matchdict.get("version", release.version):
        return HTTPMovedPermanently(
            request.current_route_path(
                name=project.name,
                version=release.version,
            ),
        )

    # It's possible that the requested version was correct (or not provided),
    # but we still need to adjust the project name.
    if project.name != request.matchdict.get("name", project.name):
        return HTTPMovedPermanently(
            request.current_route_path(name=project.name),
        )

    # Render the release description.
    description = readme.render(
        release.description, release.description_content_type)

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

    # Get the license from both the `Classifier` and `License` metadata fields
    license_classifiers = ', '.join(
        c.split(" :: ")[-1]
        for c in release.classifiers
        if c.startswith("License")
    )

    # Make a best effort when the entire license text is given by using the
    # first line only.
    short_license = release.license.split('\n')[0] if release.license else None

    if license_classifiers and short_license:
        license = f'{license_classifiers} ({short_license})'
    else:
        license = license_classifiers or short_license or None

    return {
        "project": project,
        "release": release,
        "description": description,
        "files": release.files.all(),
        "latest_version": project.latest_version,
        "all_versions": project.all_versions,
        "maintainers": maintainers,
        "license": license,
    }


@view_config(
    route_name="includes.edit-project-button",
    context=Project,
    renderer="includes/manage-project-button.html",
    uses_session=True,
    permission="manage",
)
def edit_project_button(project, request):
    return {'project': project}
