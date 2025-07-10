# SPDX-License-Identifier: Apache-2.0

import re

from pyramid.httpexceptions import HTTPSeeOther
from sqlalchemy.sql import func

from warehouse.accounts.services import IUserService
from warehouse.events.tags import EventTag
from warehouse.packaging.interfaces import IDocsStorage
from warehouse.packaging.models import (
    JournalEntry,
    LifecycleStatus,
    ProhibitedProjectName,
    Project,
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


PROJECT_NAME_RE = re.compile(
    r"^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])\Z", re.IGNORECASE
)


def confirm_project(
    project,
    request,
    fail_route,
    field_name="confirm_project_name",
    error_message="Could not delete project",
):
    confirm = request.POST.get(field_name, "").strip()
    if not confirm:
        request.session.flash("Confirm the request", queue="error")
        raise HTTPSeeOther(
            request.route_path(
                fail_route,
                project_name=project.normalized_name,
            )
        )

    project_name = project.name.strip()
    if confirm != project_name:
        request.session.flash(
            f"{error_message} - {confirm!r} is not the same as {project_name!r}",
            queue="error",
        )
        raise HTTPSeeOther(
            request.route_path(
                fail_route,
                project_name=project.normalized_name,
            )
        )


def prohibit_and_remove_project(
    project: Project | str,
    request,
    comment: str | None = None,
    observation_kind: str | None = None,
    flash: bool = True,
):
    """
    View helper to prohibit and remove a project.
    """
    # TODO: See if we can constrain `project` to be a `Project` only.
    project_name = project.name if isinstance(project, Project) else project
    # Add our requested prohibition.
    request.db.add(
        ProhibitedProjectName(
            name=project_name,
            comment=comment,
            observation_kind=observation_kind,
            prohibited_by=request.user,
        )
    )
    # Go through and delete the project and everything related to it so that
    # our prohibition actually blocks things and isn't ignored (since the
    # prohibition only takes effect on new project registration).
    project = (
        request.db.query(Project)
        .filter(Project.normalized_name == func.normalize_pep426_name(project_name))
        .first()
    )
    if project is not None:
        remove_project(project, request, flash=flash)


def quarantine_project(project: Project, request, flash=True) -> None:
    """
    Quarantine a project. Reversible action.
    """
    # TODO: This should probably be extracted to somewhere more general for tasks,
    #  but it got confusing where to add it in the context of this PR.
    #  Since JournalEntry has FK to `User`, it needs to be a real object.
    user_service = request.find_service(IUserService)
    actor = request.user or user_service.get_admin_user()

    project.lifecycle_status = LifecycleStatus.QuarantineEnter
    project.lifecycle_status_note = f"Quarantined by {actor.username}."

    project.record_event(
        tag=EventTag.Project.ProjectQuarantineEnter,
        request=request,
        additional={"submitted_by": actor.username},
    )

    request.db.add(
        JournalEntry(
            name=project.name,
            action="project quarantined",
            submitted_by=actor,
        )
    )

    # freeze associated user accounts
    for user in project.users:
        user.is_frozen = True

    if flash:
        request.session.flash(
            f"Project {project.name} quarantined.\n"
            "Please update related Help Scout conversations.",
            queue="success",
        )


def clear_project_quarantine(project: Project, request, flash=True) -> None:
    """
    Remove a project from quarantine.
    """
    project.lifecycle_status = LifecycleStatus.QuarantineExit
    project.lifecycle_status_note = f"Quarantine cleared by {request.user.username}."

    project.record_event(
        tag=EventTag.Project.ProjectQuarantineExit,
        request=request,
        additional={"submitted_by": request.user.username},
    )

    request.db.add(
        JournalEntry(
            name=project.name,
            action="project quarantine cleared",
            submitted_by=request.user,
        )
    )

    if flash:
        request.session.flash(
            f"Project {project.name} quarantine cleared.\n"
            "Please update related Help Scout conversations.",
            queue="success",
        )


def remove_project(project, request, flash=True):
    # TODO: We don't actually delete files from the data store. We should add
    #       some kind of garbage collection at some point.

    request.db.add(
        JournalEntry(
            name=project.name,
            action="remove project",
            submitted_by=request.user,
        )
    )

    request.db.delete(project)
    request.db.flush()  # flush db now so we can repeat if necessary

    if flash:
        request.session.flash(f"Deleted the project {project.name!r}", queue="success")


def destroy_docs(project, request, flash=True):
    request.task(remove_documentation).delay(project.name)
    request.task(remove_documentation).delay(project.normalized_name)

    project.has_docs = False

    if flash:
        request.session.flash(
            f"Deleted docs for project {project.name!r}", queue="success"
        )


def archive_project(project: Project, request) -> None:
    if (
        project.lifecycle_status is not None
        and project.lifecycle_status != LifecycleStatus.QuarantineExit
    ):
        request.session.flash(
            f"Cannot archive project with status {project.lifecycle_status}",
            queue="error",
        )
        return

    project.lifecycle_status = LifecycleStatus.ArchivedNoindex
    project.record_event(
        tag=EventTag.Project.ProjectArchiveEnter,
        request=request,
        additional={
            "submitted_by": request.user.username,
        },
    )
    request.session.flash("Project archived", queue="success")


def unarchive_project(project: Project, request) -> None:
    if project.lifecycle_status not in [
        LifecycleStatus.Archived,
        LifecycleStatus.ArchivedNoindex,
    ]:
        request.session.flash(
            "Can only unarchive an archived project",
            queue="error",
        )
        return

    project.lifecycle_status = None
    project.record_event(
        tag=EventTag.Project.ProjectArchiveExit,
        request=request,
        additional={
            "submitted_by": request.user.username,
        },
    )
    request.session.flash("Project unarchived", queue="success")
