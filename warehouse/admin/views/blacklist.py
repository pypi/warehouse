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

import shlex

from packaging.utils import canonicalize_name
from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest, HTTPSeeOther, HTTPNotFound
from pyramid.view import view_config
from sqlalchemy import func, or_
from sqlalchemy.orm.exc import NoResultFound

from warehouse.accounts.models import User
from warehouse.packaging.models import (
    Project, Release, File, Role, BlacklistedProject
)
from warehouse.utils.http import is_safe_url
from warehouse.utils.paginate import paginate_url_factory
from warehouse.utils.project import remove_project


@view_config(
    route_name="admin.blacklist.list",
    renderer="admin/blacklist/list.html",
    permission="admin",
    uses_session=True,
)
def blacklist(request):
    q = request.params.get("q")

    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.") from None

    blacklist_query = (
        request.db.query(BlacklistedProject)
                  .order_by(BlacklistedProject.name)
    )

    if q:
        terms = shlex.split(q)

        filters = []
        for term in terms:
            filters.append(
                BlacklistedProject.name.ilike(func.normalize_pep426_name(term))
            )

        blacklist_query = blacklist_query.filter(or_(*filters))

    blacklist = SQLAlchemyORMPage(
        blacklist_query,
        page=page_num,
        items_per_page=25,
        url_maker=paginate_url_factory(request),
    )

    return {"blacklist": blacklist, "query": q}


@view_config(
    route_name="admin.blacklist.add",
    renderer="admin/blacklist/confirm.html",
    permission="admin",
    request_method="GET",
    uses_session=True,
)
def confirm_blacklist(request):
    project_name = request.GET.get("project")
    if project_name is None:
        raise HTTPBadRequest("Must have a project to confirm.")

    comment = request.GET.get("comment", "")

    # We need to look up to see if there is an existing project, releases,
    # files, roles, etc for what we're attempting to blacklist. If there is we
    # need to warn that blacklisting will delete those.
    project = (
        request.db.query(Project)
                  .filter(Project.normalized_name ==
                          func.normalize_pep426_name(project_name))
                  .first()
    )
    if project is not None:
        releases = (
            request.db.query(Release)
                      .filter(Release.name == project.name)
                      .all()
        )
        files = (
            request.db.query(File)
                      .filter(File.name == project.name)
                      .all()
        )
        roles = (
            request.db.query(Role)
                      .join(User)
                      .filter(Role.project == project)
                      .distinct(User.username)
                      .order_by(User.username)
                      .all()
        )
    else:
        releases = []
        files = []
        roles = []

    return {
        "blacklist": {
            "project": project_name,
            "comment": comment,
        },
        "existing": {
            "project": project,
            "releases": releases,
            "files": files,
            "roles": roles,
        }
    }


@view_config(
    route_name="admin.blacklist.add",
    permission="admin",
    request_method="POST",
    uses_session=True,
    require_methods=False,
)
def add_blacklist(request):
    project_name = request.POST.get("project")
    if project_name is None:
        raise HTTPBadRequest("Must have a project to confirm.")
    comment = request.POST.get("comment", "")

    # Verify that the user has confirmed the request to blacklist.
    confirm = request.POST.get("confirm")
    if not confirm:
        request.session.flash(
            "Must confirm the blacklist request",
            queue="error",
        )
        return HTTPSeeOther(request.current_route_path())
    elif canonicalize_name(confirm) != canonicalize_name(project_name):
        request.session.flash(
            f"{confirm!r} is not the same as {project_name!r}",
            queue="error",
        )
        return HTTPSeeOther(request.current_route_path())

    # Add our requested blacklist.
    request.db.add(
        BlacklistedProject(
            name=project_name,
            comment=comment,
            blacklisted_by=request.user,
        )
    )

    # Go through and delete the project and everything related to it so that
    # our blacklist actually blocks things and isn't ignored (since the
    # blacklist only takes effect on new project registration).
    project = (
        request.db.query(Project)
                  .filter(Project.normalized_name ==
                          func.normalize_pep426_name(project_name))
                  .first()
    )
    if project is not None:
        remove_project(project, request)

    request.session.flash(
        f"Successfully blacklisted {project_name!r}",
        queue="success",
    )

    return HTTPSeeOther(request.route_path("admin.blacklist.list"))


@view_config(
    route_name="admin.blacklist.remove",
    permission="admin",
    request_method="POST",
    uses_session=True,
    require_methods=False,
)
def remove_blacklist(request):
    blacklist_id = request.POST.get("blacklist_id")
    if blacklist_id is None:
        raise HTTPBadRequest("Must have a blacklist_id to remove.")

    try:
        blacklist = (
            request.db.query(BlacklistedProject)
                      .filter(BlacklistedProject.id == blacklist_id)
                      .one()
        )
    except NoResultFound:
        raise HTTPNotFound from None

    request.db.delete(blacklist)

    request.session.flash(
        f"{blacklist.name!r} successfully unblacklisted",
        queue="success",
    )

    redirect_to = request.POST.get("next")
    # If the user-originating redirection url is not safe, then redirect to
    # the index instead.
    if (not redirect_to or
            not is_safe_url(url=redirect_to, host=request.host)):
        redirect_to = request.route_path("admin.blacklist.list")

    return HTTPSeeOther(redirect_to)
