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

from collections import defaultdict

from packaging.utils import canonicalize_name
from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPSeeOther
from pyramid.view import view_config
from sqlalchemy import func, literal, or_
from sqlalchemy.exc import NoResultFound

from warehouse.accounts.models import User
from warehouse.authnz import Permissions
from warehouse.packaging.models import (
    File,
    ProhibitedProjectName,
    Project,
    Release,
    Role,
)
from warehouse.utils.http import is_safe_url
from warehouse.utils.paginate import paginate_url_factory
from warehouse.utils.project import prohibit_and_remove_project


@view_config(
    route_name="admin.prohibited_project_names.list",
    renderer="admin/prohibited_project_names/list.html",
    permission=Permissions.AdminProhibitedProjectsRead,
    request_method="GET",
    uses_session=True,
)
def prohibited_project_names(request):
    q = request.params.get("q")

    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.") from None

    prohibited_project_names_query = request.db.query(ProhibitedProjectName).order_by(
        ProhibitedProjectName.name
    )

    if q:
        terms = shlex.split(q)

        filters = []
        for term in terms:
            filters.append(
                ProhibitedProjectName.name.ilike(func.normalize_pep426_name(term))
            )

        filters = filters or [True]
        prohibited_project_names_query = prohibited_project_names_query.filter(
            or_(False, *filters)
        )

    prohibited_project_names = SQLAlchemyORMPage(
        prohibited_project_names_query,
        page=page_num,
        items_per_page=25,
        url_maker=paginate_url_factory(request),
    )

    return {"prohibited_project_names": prohibited_project_names, "query": q}


@view_config(
    route_name="admin.prohibited_project_names.add",
    renderer="admin/prohibited_project_names/confirm.html",
    permission=Permissions.AdminProhibitedProjectsWrite,
    request_method="GET",
    uses_session=True,
)
def confirm_prohibited_project_names(request):
    project_name = request.GET.get("project")
    if project_name is None:
        raise HTTPBadRequest("Have a project to confirm.")

    comment = request.GET.get("comment", "")

    # We need to look up to see if there is an existing project, releases,
    # files, roles, etc for what we're attempting to prohibit. If there is we
    # need to warn that prohibiting will delete those.
    project = (
        request.db.query(Project)
        .filter(Project.normalized_name == func.normalize_pep426_name(project_name))
        .first()
    )
    if project is not None:
        releases = (
            request.db.query(Release)
            .join(Project)
            .filter(Release.project == project)
            .all()
        )
        files = (
            request.db.query(File)
            .join(Release)
            .join(Project)
            .filter(Release.project == project)
            .all()
        )
        roles = (
            request.db.query(Role)
            .join(User)
            .join(Project)
            .filter(Role.project == project)
            .distinct(User.username)
            .order_by(User.username)
            .all()
        )
    else:
        releases = []
        files = []
        roles = []

    releases_by_date = defaultdict(list)
    for release in releases:
        releases_by_date[release.created.strftime("%Y-%m-%d")].append(release)

    return {
        "prohibited_project_names": {"project": project_name, "comment": comment},
        "existing": {
            "project": project,
            "releases": releases,
            "releases_by_date": releases_by_date,
            "files": files,
            "roles": roles,
        },
    }


@view_config(
    route_name="admin.prohibited_project_names.release",
    permission=Permissions.AdminProhibitedProjectsWrite,
    request_method="POST",
    uses_session=True,
    require_methods=False,
)
def release_prohibited_project_name(request):
    project_name = request.POST.get("project_name")
    if project_name is None:
        request.session.flash("Provide a project name", queue="error")
        return HTTPSeeOther(request.current_route_path())

    prohibited_project_name = (
        request.db.query(ProhibitedProjectName)
        .filter(ProhibitedProjectName.name == func.normalize_pep426_name(project_name))
        .first()
    )
    if prohibited_project_name is None:
        request.session.flash(
            f"{project_name!r} does not exist on prohibited project name list.",
            queue="error",
        )
        return HTTPSeeOther(request.current_route_path())

    project = (
        request.db.query(Project)
        .filter(Project.normalized_name == func.normalize_pep426_name(project_name))
        .first()
    )
    if project is not None:
        request.session.flash(
            f"{project_name!r} exists and is not on the prohibited project name list.",
            queue="error",
        )
        return HTTPSeeOther(request.current_route_path())

    username = request.POST.get("username")
    if not username:
        request.session.flash("Provide a username", queue="error")
        return HTTPSeeOther(request.current_route_path())

    user = request.db.query(User).filter(User.username == username).first()
    if user is None:
        request.session.flash(f"Unknown username '{username}'", queue="error")
        return HTTPSeeOther(request.current_route_path())

    project = Project(name=project_name)
    request.db.add(project)
    request.db.add(Role(project=project, user=user, role_name="Owner"))
    request.db.delete(prohibited_project_name)

    request.session.flash(
        f"{project.name!r} released to {user.username!r}.", queue="success"
    )

    request.db.flush()  # flush db now so project.normalized_name is available

    return HTTPSeeOther(
        request.route_path("admin.project.detail", project_name=project.normalized_name)
    )


@view_config(
    route_name="admin.prohibited_project_names.add",
    permission=Permissions.AdminProhibitedProjectsWrite,
    request_method="POST",
    uses_session=True,
    require_methods=False,
)
def add_prohibited_project_names(request):
    project_name = request.POST.get("project")
    if project_name is None:
        raise HTTPBadRequest("Have a project to confirm.")
    comment = request.POST.get("comment", "")

    # Verify that the user has confirmed the request to prohibit.
    confirm = request.POST.get("confirm")
    if not confirm:
        request.session.flash(
            "Confirm the prohibited project name request", queue="error"
        )
        return HTTPSeeOther(request.current_route_path())
    elif canonicalize_name(confirm) != canonicalize_name(project_name):
        request.session.flash(
            f"{confirm!r} is not the same as {project_name!r}", queue="error"
        )
        return HTTPSeeOther(request.current_route_path())

    # Check to make sure the object doesn't already exist.
    if (
        request.db.query(literal(True))
        .filter(
            request.db.query(ProhibitedProjectName)
            .filter(
                ProhibitedProjectName.name == func.normalize_pep426_name(project_name)
            )
            .exists()
        )
        .scalar()
    ):
        request.session.flash(
            f"{project_name!r} has already been prohibited.", queue="error"
        )
        return HTTPSeeOther(request.route_path("admin.prohibited_project_names.list"))

    prohibit_and_remove_project(project_name, request, comment)

    request.session.flash(f"Prohibited Project Name {project_name!r}", queue="success")

    return HTTPSeeOther(request.route_path("admin.prohibited_project_names.list"))


@view_config(
    route_name="admin.prohibited_project_names.remove",
    permission=Permissions.AdminProhibitedProjectsWrite,
    request_method="POST",
    uses_session=True,
    require_methods=False,
)
def remove_prohibited_project_names(request):
    prohibited_project_name_id = request.POST.get("prohibited_project_name_id")
    if prohibited_project_name_id is None:
        raise HTTPBadRequest("Have a prohibited_project_name_id to remove.")

    try:
        prohibited_project_names = (
            request.db.query(ProhibitedProjectName)
            .filter(ProhibitedProjectName.id == prohibited_project_name_id)
            .one()
        )
    except NoResultFound:
        raise HTTPNotFound from None

    request.db.delete(prohibited_project_names)

    request.session.flash(
        f"{prohibited_project_names.name!r} unprohibited", queue="success"
    )

    redirect_to = request.POST.get("next")
    # If the user-originating redirection url is not safe, then redirect to
    # the index instead.
    if not redirect_to or not is_safe_url(url=redirect_to, host=request.host):
        redirect_to = request.route_path("admin.prohibited_project_names.list")

    return HTTPSeeOther(redirect_to)


@view_config(
    route_name="admin.prohibited_project_names.bulk_add",
    renderer="admin/prohibited_project_names/bulk.html",
    permission=Permissions.AdminProhibitedProjectsWrite,
    uses_session=True,
    require_methods=False,
)
def bulk_add_prohibited_project_names(request):
    if request.method == "POST":
        project_names = request.POST.get("projects", "").split()
        comment = request.POST.get("comment", "")

        for project_name in project_names:
            # Check to make sure the object doesn't already exist.
            if (
                request.db.query(literal(True))
                .filter(
                    request.db.query(ProhibitedProjectName)
                    .filter(ProhibitedProjectName.name == project_name)
                    .exists()
                )
                .scalar()
            ):
                continue

            prohibit_and_remove_project(project_name, request, comment, flash=False)

        request.session.flash(
            f"Prohibited {len(project_names)!r} projects", queue="success"
        )

        return HTTPSeeOther(
            request.route_path("admin.prohibited_project_names.bulk_add")
        )
    return {}
