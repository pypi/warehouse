# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re

from typing import TYPE_CHECKING

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
    Release,
)
from warehouse.tasks import task

if TYPE_CHECKING:
    from pyramid.request import Request


@task(bind=True, ignore_result=True, acks_late=True)
def remove_documentation(task, request, project_name):
    request.log.info("Removing documentation for %s", project_name)
    storage = request.find_service(IDocsStorage)
    try:
        storage.remove_by_prefix(f"{project_name}/")
    except Exception as exc:  # noqa: BLE001
        task.retry(exc=exc)


PROJECT_NAME_RE = re.compile(
    r"^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])\Z", re.IGNORECASE | re.ASCII
)


def confirm_project(
    project,
    request,
    fail_route,
    field_name="confirm_project_name",
    error_message="Could not delete project",
    **fail_route_params,
):
    """
    Require the user to retype a project's name to confirm a destructive action.

    Raises ``HTTPSeeOther`` to ``fail_route`` when the confirmation is missing
    or wrong. ``fail_route_params`` are the keyword arguments used to build that
    redirect; they default to ``project_name`` for project-keyed routes, but an
    observation-scoped route can pass ``observation_id`` instead.
    """
    fail_route_params = fail_route_params or {"project_name": project.normalized_name}

    confirm = request.POST.get(field_name, "").strip()
    if not confirm:
        request.session.flash("Confirm the request", queue="error")
        raise HTTPSeeOther(request.route_path(fail_route, **fail_route_params))

    project_name = project.name.strip()
    if confirm != project_name:
        request.session.flash(
            f"{error_message} - {confirm!r} is not the same as {project_name!r}",
            queue="error",
        )
        raise HTTPSeeOther(request.route_path(fail_route, **fail_route_params))


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


def quarantine_release(release: Release, request, flash: bool = True) -> None:
    """
    Quarantine a single release. Reversible action.

    Mirrors :func:`quarantine_project` but scoped to a specific release. The
    parent project is unaffected so other releases remain installable.
    """
    user_service = request.find_service(IUserService)
    actor = request.user or user_service.get_admin_user()

    release.lifecycle_status = LifecycleStatus.QuarantineEnter
    release.lifecycle_status_note = f"Quarantined by {actor.username}."

    release.project.record_event(
        tag=EventTag.Project.ReleaseQuarantineEnter,
        request=request,
        additional={
            "submitted_by": actor.username,
            "canonical_version": release.canonical_version,
            "version": release.version,
        },
    )

    request.db.add(
        JournalEntry(
            name=release.project.name,
            version=release.version,
            action="release quarantined",
            submitted_by=actor,
        )
    )

    if flash:
        request.session.flash(
            f"Release {release.version} of {release.project.name} quarantined.",
            queue="success",
        )


def clear_release_quarantine(release: Release, request, flash: bool = True) -> None:
    """
    Remove a release from quarantine.
    """
    release.lifecycle_status = LifecycleStatus.QuarantineExit
    release.lifecycle_status_note = f"Quarantine cleared by {request.user.username}."

    release.project.record_event(
        tag=EventTag.Project.ReleaseQuarantineExit,
        request=request,
        additional={
            "submitted_by": request.user.username,
            "canonical_version": release.canonical_version,
            "version": release.version,
        },
    )

    request.db.add(
        JournalEntry(
            name=release.project.name,
            version=release.version,
            action="release quarantine cleared",
            submitted_by=request.user,
        )
    )

    if flash:
        request.session.flash(
            f"Release {release.version} of {release.project.name} quarantine cleared.",
            queue="success",
        )


def remove_release(release: Release, request: Request, *, reason: str) -> None:
    """
    Delete a single release.

    Records a journal entry, emits the ``ReleaseRemove`` event, and deletes
    the row. Mirrors :func:`remove_project`: contributor notifications are
    the caller's choice, so a non-malware admin path can email owners while
    a malware verdict stays silent.
    """
    request.db.add(
        JournalEntry(
            name=release.project.name,
            action="remove release",
            version=release.version,
            submitted_by=request.user,
        )
    )

    release.project.record_event(
        tag=EventTag.Project.ReleaseRemove,
        request=request,
        additional={
            "submitted_by": request.user.username,
            "canonical_version": release.canonical_version,
            "reason": reason,
        },
    )

    request.db.delete(release)


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
