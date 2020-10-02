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

from pyramid.httpexceptions import (
    HTTPMovedPermanently,
    HTTPNotFound,
    HTTPTemporaryRedirect,
)
from pyramid.view import view_config
from sqlalchemy.orm.exc import NoResultFound

from warehouse.accounts.models import User
from warehouse.cache.origin import origin_cache
from warehouse.packaging.models import Project, Release, Role
from warehouse.utils import readme


@view_config(
    route_name="packaging.project",
    context=Project,
    renderer="packaging/detail.html",
    decorator=[
        origin_cache(
            1 * 24 * 60 * 60, stale_if_error=5 * 24 * 60 * 60  # 1 day, 5 days stale
        )
    ],
    has_translations=True,
)
def project_detail(project, request):
    if project.name != request.matchdict.get("name", project.name):
        return HTTPMovedPermanently(request.current_route_path(name=project.name))

    try:
        release = (
            request.db.query(Release)
            .filter(Release.project == project)
            .order_by(
                Release.yanked,
                Release.is_prerelease.nullslast(),
                Release._pypi_ordering.desc(),
            )
            .limit(1)
            .one()
        )
    except NoResultFound:
        raise HTTPNotFound

    return release_detail(release, request)


@view_config(
    route_name="packaging.project_latest",
    context=Project,
)
def project_latest(project, request):
    return HTTPTemporaryRedirect(
        request.route_path(
            "packaging.release",
            name=project.name,
            version=project.latest_version.version,
        )
    )


@view_config(
    route_name="packaging.project_latest_stable",
    context=Project,
)
def project_latest_stable(project, request):
    release = project.latest_stable_version

    if release:
        return HTTPTemporaryRedirect(
            request.route_path(
                "packaging.release",
                name=project.name,
                version=project.latest_stable_version.version,
            )
        )
    else:
        return HTTPNotFound()


@view_config(
    route_name="packaging.project_latest_unstable",
    context=Project,
)
def project_latest_unstable(project, request):
    return HTTPTemporaryRedirect(
        request.route_path(
            "packaging.release",
            name=project.name,
            version=project.latest_unstable_version.version,
        )
    )


@view_config(
    route_name="packaging.release",
    context=Release,
    renderer="packaging/detail.html",
    decorator=[
        origin_cache(
            1 * 24 * 60 * 60, stale_if_error=5 * 24 * 60 * 60  # 1 day, 5 days stale
        )
    ],
    has_translations=True,
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
            request.current_route_path(name=project.name, version=release.version)
        )

    # It's possible that the requested version was correct (or not provided),
    # but we still need to adjust the project name.
    if project.name != request.matchdict.get("name", project.name):
        return HTTPMovedPermanently(request.current_route_path(name=project.name))

    # Grab the rendered description if it exists, and if it doesn't, then we will render
    # it inline.
    # TODO: Remove the fallback to rendering inline and only support displaying the
    #       already rendered content.
    if release.description.html:
        description = release.description.html
    else:
        description = readme.render(
            release.description.raw, release.description.content_type
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

    # Get the license from both the `Classifier` and `License` metadata fields
    license_classifiers = ", ".join(
        c.split(" :: ")[-1] for c in release.classifiers if c.startswith("License")
    )

    # Make a best effort when the entire license text is given by using the
    # first line only.
    short_license = release.license.split("\n")[0] if release.license else None

    if license_classifiers and short_license:
        license = f"{license_classifiers} ({short_license})"
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
    permission="manage:project",
    has_translations=True,
)
def edit_project_button(project, request):
    return {"project": project}
