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

from itertools import chain

import stdlib_list

from packaging.utils import canonicalize_name
from pyramid.httpexceptions import HTTPBadRequest, HTTPForbidden, HTTPSeeOther
from sqlalchemy import exists, func
from sqlalchemy.orm.exc import NoResultFound

from warehouse.admin.flags import AdminFlagValue
from warehouse.packaging.interfaces import IDocsStorage
from warehouse.packaging.models import (
    JournalEntry,
    ProhibitedProjectName,
    Project,
    Role,
)
from warehouse.tasks import task


@task(bind=True, ignore_result=True, acks_late=True)
def remove_documentation(task, request, project_name):
    request.log.info("Removing documentation for %s", project_name)
    storage = request.find_service(IDocsStorage)
    try:
        storage.remove_by_prefix(f"{project_name}/")
    except Exception as exc:
        task.retry(exc=exc)


def _namespace_stdlib_list(module_list):
    for module_name in module_list:
        parts = module_name.split(".")
        for i, part in enumerate(parts):
            yield ".".join(parts[: i + 1])


STDLIB_PROHIBITED = {
    canonicalize_name(s.rstrip("-_.").lstrip("-_."))
    for s in chain.from_iterable(
        _namespace_stdlib_list(stdlib_list.stdlib_list(version))
        for version in stdlib_list.short_versions
    )
}


def add_project(name, request):
    """
    Attempts to create a project with the given name.
    """
    # Look up the project first before doing anything else, this is so we can
    # automatically register it if we need to and can check permissions before
    # going any further.
    try:
        project = (
            request.db.query(Project)
            .filter(Project.normalized_name == func.normalize_pep426_name(name))
            .one()
        )
    except NoResultFound:
        # Check for AdminFlag set by a PyPI Administrator disabling new project
        # registration, reasons for this include Spammers, security
        # vulnerabilities, or just wanting to be lazy and not worry ;)
        if request.flags.enabled(AdminFlagValue.DISALLOW_NEW_PROJECT_REGISTRATION):
            raise HTTPForbidden(
                (
                    "New project registration temporarily disabled. "
                    "See {projecthelp} for more information."
                ).format(projecthelp=request.help_url(_anchor="admin-intervention")),
            ) from None

        # Before we create the project, we're going to check our prohibited
        # names to see if this project name prohibited, or if the project name
        # is a close approximation of an existing project name. If it is,
        # then we're going to deny the request to create this project.
        _prohibited_name = request.db.query(
            exists().where(
                ProhibitedProjectName.name == func.normalize_pep426_name(name)
            )
        ).scalar()
        if _prohibited_name:
            raise HTTPBadRequest(
                (
                    "The name {name!r} isn't allowed. "
                    "See {projecthelp} for more information."
                ).format(
                    name=name,
                    projecthelp=request.help_url(_anchor="project-name"),
                ),
            ) from None

        _ultranormalize_collision = request.db.query(
            exists().where(
                func.ultranormalize_name(Project.name) == func.ultranormalize_name(name)
            )
        ).scalar()
        if _ultranormalize_collision:
            raise HTTPBadRequest(
                (
                    "The name {name!r} is too similar to an existing project. "
                    "See {projecthelp} for more information."
                ).format(
                    name=name,
                    projecthelp=request.help_url(_anchor="project-name"),
                ),
            ) from None

        # Also check for collisions with Python Standard Library modules.
        if canonicalize_name(name) in STDLIB_PROHIBITED:
            raise HTTPBadRequest(
                (
                    "The name {name!r} isn't allowed (conflict with Python "
                    "Standard Library module name). See "
                    "{projecthelp} for more information."
                ).format(
                    name=name,
                    projecthelp=request.help_url(_anchor="project-name"),
                ),
            ) from None

        # Next we'll create the project
        project = Project(name=name)
        request.db.add(project)

        # Then we'll add a role setting the current user as the "Owner" of the
        # project.
        request.db.add(Role(user=request.user, project=project, role_name="Owner"))
        # TODO: This should be handled by some sort of database trigger or a
        #       SQLAlchemy hook or the like instead of doing it inline in this
        #       view.
        request.db.add(
            JournalEntry(
                name=project.name,
                action="create",
                submitted_by=request.user,
                submitted_from=request.remote_addr,
            )
        )
        request.db.add(
            JournalEntry(
                name=project.name,
                action="add Owner {}".format(request.user.username),
                submitted_by=request.user,
                submitted_from=request.remote_addr,
            )
        )

        project.record_event(
            tag="project:create",
            ip_address=request.remote_addr,
            additional={"created_by": request.user.username},
        )
        project.record_event(
            tag="project:role:add",
            ip_address=request.remote_addr,
            additional={
                "submitted_by": request.user.username,
                "role_name": "Owner",
                "target_user": request.user.username,
            },
        )

    return project


def confirm_project(
    project,
    request,
    fail_route,
    field_name="confirm_project_name",
    error_message="Could not delete project",
):
    confirm = request.POST.get(field_name)
    project_name = project.normalized_name
    if not confirm:
        request.session.flash("Confirm the request", queue="error")
        raise HTTPSeeOther(request.route_path(fail_route, project_name=project_name))
    if canonicalize_name(confirm) != project.normalized_name:
        request.session.flash(
            f"{error_message} - "
            + f"{confirm!r} is not the same as {project.normalized_name!r}",
            queue="error",
        )
        raise HTTPSeeOther(request.route_path(fail_route, project_name=project_name))


def remove_project(project, request, flash=True):
    # TODO: We don't actually delete files from the data store. We should add
    #       some kind of garbage collection at some point.

    request.db.add(
        JournalEntry(
            name=project.name,
            action="remove project",
            submitted_by=request.user,
            submitted_from=request.remote_addr,
        )
    )

    request.db.delete(project)

    # Flush so we can repeat this multiple times if necessary
    request.db.flush()

    if flash:
        request.session.flash(f"Deleted the project {project.name!r}", queue="success")


def destroy_docs(project, request, flash=True):
    request.db.add(
        JournalEntry(
            name=project.name,
            action="docdestroy",
            submitted_by=request.user,
            submitted_from=request.remote_addr,
        )
    )

    request.task(remove_documentation).delay(project.name)

    project.has_docs = False

    if flash:
        request.session.flash(
            f"Deleted docs for project {project.name!r}", queue="success"
        )
