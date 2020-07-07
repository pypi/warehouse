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

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest, HTTPMovedPermanently, HTTPSeeOther
from pyramid.view import view_config
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import NoResultFound

from warehouse.accounts.models import User
from warehouse.forklift.legacy import MAX_FILESIZE, MAX_PROJECT_SIZE
from warehouse.packaging.models import JournalEntry, Project, Release, Role
from warehouse.utils.paginate import paginate_url_factory
from warehouse.utils.project import confirm_project, destroy_project, soft_restore_project

ONE_MB = 1024 * 1024  # bytes
ONE_GB = 1024 * 1024 * 1024  # bytes


@view_config(
    route_name="admin.project.list",
    renderer="admin/projects/list.html",
    permission="moderator",
    request_method="GET",
    uses_session=True,
)
def project_list(request):
    q = request.params.get("q")

    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.") from None

    projects_query = request.db.query(Project).order_by(Project.normalized_name)

    if q:
        terms = shlex.split(q)

        filters = []
        for term in terms:
            filters.append(Project.name.ilike(term))

        projects_query = projects_query.filter(or_(*filters))

    projects = SQLAlchemyORMPage(
        projects_query,
        page=page_num,
        items_per_page=25,
        url_maker=paginate_url_factory(request),
    )

    return {"projects": projects, "query": q}


@view_config(
    route_name="admin.project.detail",
    renderer="admin/projects/detail.html",
    permission="moderator",
    request_method="GET",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
@view_config(
    route_name="admin.project.detail",
    renderer="admin/projects/detail.html",
    permission="admin",
    request_method="POST",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
)
def project_detail(project, request):
    project_name = request.matchdict["project_name"]

    if project_name != project.normalized_name:
        raise HTTPMovedPermanently(
            request.current_route_path(project_name=project.normalized_name)
        )

    releases = (
        request.db.query(Release)
        .filter(Release.project == project)
        .order_by(Release._pypi_ordering.desc())
        .limit(10)
        .all()
    )

    maintainers = [
        role
        for role in (
            request.db.query(Role)
            .join(User)
            .filter(Role.project == project)
            .distinct(User.username)
            .all()
        )
    ]
    maintainers = sorted(maintainers, key=lambda x: (x.role_name, x.user.username))
    journal = [
        entry
        for entry in (
            request.db.query(JournalEntry)
            .options(joinedload("submitted_by"))
            .filter(JournalEntry.name == project.name)
            .order_by(JournalEntry.submitted_date.desc(), JournalEntry.id.desc())
            .limit(30)
        )
    ]

    squattees = (
        request.db.query(Project)
        .filter(Project.created < project.created)
        .filter(func.levenshtein(Project.normalized_name, project.normalized_name) <= 2)
        .all()
    )

    squatters = (
        request.db.query(Project)
        .filter(Project.created > project.created)
        .filter(func.levenshtein(Project.normalized_name, project.normalized_name) <= 2)
        .all()
    )

    return {
        "project": project,
        "releases": releases,
        "maintainers": maintainers,
        "journal": journal,
        "squatters": squatters,
        "squattees": squattees,
        "ONE_MB": ONE_MB,
        "MAX_FILESIZE": MAX_FILESIZE,
        "ONE_GB": ONE_GB,
        "MAX_PROJECT_SIZE": MAX_PROJECT_SIZE,
    }


@view_config(
    route_name="admin.project.releases",
    renderer="admin/projects/releases_list.html",
    permission="moderator",
    request_method="GET",
    uses_session=True,
)
def releases_list(project, request):
    q = request.params.get("q")
    project_name = request.matchdict["project_name"]

    if project_name != project.normalized_name:
        raise HTTPMovedPermanently(
            request.current_route_path(project_name=project.normalized_name)
        )

    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.") from None

    releases_query = (
        request.db.query(Release)
        .filter(Release.project == project)
        .order_by(Release._pypi_ordering.desc())
    )

    if q:
        terms = shlex.split(q)

        filters = []
        for term in terms:
            if ":" in term:
                field, value = term.split(":", 1)
                if field.lower() == "version":
                    filters.append(Release.version.ilike(value))

        releases_query = releases_query.filter(or_(*filters))

    releases = SQLAlchemyORMPage(
        releases_query,
        page=page_num,
        items_per_page=25,
        url_maker=paginate_url_factory(request),
    )

    return {"releases": releases, "project": project, "query": q}


@view_config(
    route_name="admin.project.release",
    renderer="admin/projects/release_detail.html",
    permission="moderator",
    request_method="GET",
    uses_session=True,
)
def release_detail(release, request):
    journals = (
        request.db.query(JournalEntry)
        .options(joinedload("submitted_by"))
        .filter(JournalEntry.name == release.project.name)
        .filter(JournalEntry.version == release.version)
        .order_by(JournalEntry.submitted_date.desc(), JournalEntry.id.desc())
        .all()
    )
    return {"release": release, "journals": journals}


@view_config(
    route_name="admin.project.journals",
    renderer="admin/projects/journals_list.html",
    permission="moderator",
    request_method="GET",
    uses_session=True,
)
def journals_list(project, request):
    q = request.params.get("q")
    project_name = request.matchdict["project_name"]

    if project_name != project.normalized_name:
        raise HTTPMovedPermanently(
            request.current_route_path(project_name=project.normalized_name)
        )

    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.") from None

    journals_query = (
        request.db.query(JournalEntry)
        .options(joinedload("submitted_by"))
        .filter(JournalEntry.name == project.name)
        .order_by(JournalEntry.submitted_date.desc(), JournalEntry.id.desc())
    )

    if q:
        terms = shlex.split(q)

        filters = []
        for term in terms:
            if ":" in term:
                field, value = term.split(":", 1)
                if field.lower() == "version":
                    filters.append(JournalEntry.version.ilike(value))

        journals_query = journals_query.filter(or_(*filters))

    journals = SQLAlchemyORMPage(
        journals_query,
        page=page_num,
        items_per_page=25,
        url_maker=paginate_url_factory(request),
    )

    return {"journals": journals, "project": project, "query": q}


@view_config(
    route_name="admin.project.set_upload_limit",
    permission="moderator",
    request_method="POST",
    uses_session=True,
    require_methods=False,
)
def set_upload_limit(project, request):
    upload_limit = request.POST.get("upload_limit", "")

    # Update the project's upload limit.
    # If the upload limit is an empty string or otherwise falsy, just set the
    # limit to None, indicating the default limit.
    if not upload_limit:
        upload_limit = None
    else:
        try:
            upload_limit = int(upload_limit)
        except ValueError:
            raise HTTPBadRequest(
                f"Invalid value for upload limit: {upload_limit}, "
                f"must be integer or empty string."
            )

        # The form is in MB, but the database field is in bytes.
        upload_limit *= ONE_MB

        if upload_limit < MAX_FILESIZE:
            raise HTTPBadRequest(
                f"Upload limit can not be less than the default limit of "
                f"{MAX_FILESIZE / ONE_MB}MB."
            )

    project.upload_limit = upload_limit

    request.session.flash(f"Set the upload limit on {project.name!r}", queue="success")

    return HTTPSeeOther(
        request.route_path("admin.project.detail", project_name=project.normalized_name)
    )


@view_config(
    route_name="admin.project.set_total_size_limit",
    permission="moderator",
    request_method="POST",
    uses_session=True,
    require_methods=False,
)
def set_total_size_limit(project, request):
    total_size_limit = request.POST.get("total_size_limit", "")

    if not total_size_limit:
        total_size_limit = None
    else:
        try:
            total_size_limit = int(total_size_limit)
        except ValueError:
            raise HTTPBadRequest(
                f"Invalid value for total size limit: {total_size_limit}, "
                f"must be integer or empty string."
            )

        # The form is in GB, but the database field is in bytes.
        total_size_limit *= ONE_GB

        if total_size_limit < MAX_PROJECT_SIZE:
            raise HTTPBadRequest(
                f"Total project size can not be less than the default limit of "
                f"{MAX_PROJECT_SIZE / ONE_GB}GB."
            )

    project.total_size_limit = total_size_limit

    request.session.flash(
        f"Set the total size limit on {project.name!r}", queue="success"
    )

    return HTTPSeeOther(
        request.route_path("admin.project.detail", project_name=project.normalized_name)
    )


@view_config(
    route_name="admin.project.add_role",
    permission="admin",
    request_method="POST",
    uses_session=True,
    require_methods=False,
)
def add_role(project, request):
    username = request.POST.get("username")
    if not username:
        request.session.flash("Provide a username", queue="error")
        raise HTTPSeeOther(
            request.route_path(
                "admin.project.detail", project_name=project.normalized_name
            )
        )

    try:
        user = request.db.query(User).filter(User.username == username).one()
    except NoResultFound:
        request.session.flash(f"Unknown username '{username}'", queue="error")
        raise HTTPSeeOther(
            request.route_path(
                "admin.project.detail", project_name=project.normalized_name
            )
        )

    role_name = request.POST.get("role_name")
    if not role_name:
        request.session.flash("Provide a role", queue="error")
        raise HTTPSeeOther(
            request.route_path(
                "admin.project.detail", project_name=project.normalized_name
            )
        )

    already_there = (
        request.db.query(Role)
        .filter(Role.user == user, Role.project == project)
        .count()
    )

    if already_there > 0:
        request.session.flash(
            f"User '{user.username}' already has a role on this project", queue="error"
        )
        raise HTTPSeeOther(
            request.route_path(
                "admin.project.detail", project_name=project.normalized_name
            )
        )

    request.db.add(
        JournalEntry(
            name=project.name,
            action=f"add {role_name} {user.username}",
            submitted_by=request.user,
            submitted_from=request.remote_addr,
        )
    )

    request.db.add(Role(role_name=role_name, user=user, project=project))

    request.session.flash(
        f"Added '{user.username}' as '{role_name}' on '{project.name}'", queue="success"
    )
    return HTTPSeeOther(
        request.route_path("admin.project.detail", project_name=project.normalized_name)
    )


@view_config(
    route_name="admin.project.delete_role",
    permission="admin",
    request_method="POST",
    uses_session=True,
    require_methods=False,
)
def delete_role(project, request):
    confirm = request.POST.get("username")
    role_id = request.matchdict.get("role_id")

    role = request.db.query(Role).get(role_id)
    if not role:
        request.session.flash("This role no longer exists", queue="error")
        raise HTTPSeeOther(
            request.route_path(
                "admin.project.detail", project_name=project.normalized_name
            )
        )

    if not confirm or confirm != role.user.username:
        request.session.flash("Confirm the request", queue="error")
        raise HTTPSeeOther(
            request.route_path(
                "admin.project.detail", project_name=project.normalized_name
            )
        )

    request.session.flash(
        f"Removed '{role.user.username}' as '{role.role_name}' on '{project.name}'",
        queue="success",
    )
    request.db.add(
        JournalEntry(
            name=project.name,
            action=f"remove {role.role_name} {role.user.username}",
            submitted_by=request.user,
            submitted_from=request.remote_addr,
        )
    )

    request.db.delete(role)

    return HTTPSeeOther(
        request.route_path("admin.project.detail", project_name=project.normalized_name)
    )



@view_config(
    route_name="admin.project.restore",
    permission="admin",
    request_method="POST",
    uses_session=True,
    require_methods=False,
)
def restore_project(project, request):
    confirm_project(project, request, fail_route="admin.project.detail")
    soft_restore_project(project, request)

    return HTTPSeeOther(request.route_path("admin.project.list"))



@view_config(
    route_name="admin.project.delete",
    permission="admin",
    request_method="POST",
    uses_session=True,
    require_methods=False,
)
def delete_project(project, request):
    confirm_project(project, request, fail_route="admin.project.detail")
    destroy_project(project, request)

    return HTTPSeeOther(request.route_path("admin.project.list"))
