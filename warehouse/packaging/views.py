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

from datetime import datetime
from pyramid.httpexceptions import (
    HTTPFound, HTTPMovedPermanently, HTTPNotFound, HTTPSeeOther, HTTPForbidden
)
from pyramid.view import view_config
from sqlalchemy.orm.exc import NoResultFound

from warehouse.accounts.models import User
from warehouse.accounts import REDIRECT_FIELD_NAME

from warehouse.cache.origin import origin_cache
from warehouse.packaging.models import Release, Role
from warehouse.packaging.forms import DeprecationForm


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
                      .order_by(Release._pypi_ordering.desc())
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

    if project.name != request.matchdict.get("name", project.name):
        return HTTPMovedPermanently(
            request.current_route_path(name=project.name),
        )

    # Get all of the registered versions for this Project, in order of newest
    # to oldest.
    all_releases = (
        request.db.query(Release)
                  .filter(Release.project == project)
                  .with_entities(Release.version, Release.created,
                                 Release.deprecated_reason)
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
        "all_releases": all_releases,
        "maintainers": maintainers,
        "license": license,
    }


@view_config(
    route_name="packaging.deprecate",
    renderer="packaging/deprecate.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def deprecate(project, request, _form_class=DeprecationForm):

    # if the user is not logged in, return a redirect to the login page with
    # the REDIRECT_URL pointing as parameter that points back to this view.
    if request.authenticated_userid is None:
        url = request.route_url(
            "accounts.login",
            _query={REDIRECT_FIELD_NAME: request.path_qs},
        )
        return HTTPSeeOther(url)

    # check that the currently logged in user belongs to the project. If this
    # isn't the case, return early with a 403
    project_userids = [str(p.id) for p in project.users]
    if request.authenticated_userid not in project_userids:
        return HTTPForbidden()

    deprecated_releases = [
        r for r in project.releases if r.deprecated_at is not None
    ]
    # instantiate and populate the form data with all available releases
    # that have not yet been deprecated
    form = _form_class(data=request.POST)
    form.release.choices = [
        (r.version, r.version) for r in project.releases
        if r not in deprecated_releases
    ]

    if request.method == "POST" and form.validate():
        # update the release
        release = next(
            filter(lambda r: r.version == form.release.data, project.releases)
        )
        release.deprecated_at = datetime.now()
        release.deprecated_reason = form.reason.data
        release.deprecated_url = form.url.data

        # redirect to back to this view. This saves us some code because we
        # don't have to re-populate the form and the context for the updated
        # release
        return HTTPFound(
            request.route_url("packaging.deprecate", name=project.name)
        )

    return {
        "project": project,
        "deprecated_releases": deprecated_releases,
        "form": form
    }
