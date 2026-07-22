# SPDX-License-Identifier: Apache-2.0

import pytest

from pyramid.httpexceptions import HTTPSeeOther
from sqlalchemy.orm import joinedload

from warehouse.events.tags import EventTag
from warehouse.packaging.models import (
    Dependency,
    File,
    JournalEntry,
    LifecycleStatus,
    Project,
    Release,
    Role,
)
from warehouse.utils.project import (
    PROJECT_NAME_RE,
    clear_project_quarantine,
    clear_release_quarantine,
    confirm_project,
    deprecate_project,
    destroy_docs,
    quarantine_project,
    quarantine_release,
    remove_documentation,
    remove_project,
    remove_release,
    undeprecate_project,
)

from ...common.db.accounts import UserFactory
from ...common.db.packaging import (
    DependencyFactory,
    FileFactory,
    ProjectFactory,
    ReleaseFactory,
    RoleFactory,
)


@pytest.mark.parametrize(
    "name", ["django", "zope.interface", "Twisted", "foo_bar", "abc123"]
)
def test_project_name_re_ok(name: str) -> None:
    assert PROJECT_NAME_RE.match(name) is not None


@pytest.mark.parametrize("name", ["", "foo\n", "foo\nbar", "..."])
def test_project_name_re_invalid(name: str) -> None:
    assert PROJECT_NAME_RE.match(name) is None


def test_confirm(pyramid_request, mocker):
    project = Project(name="foobar", normalized_name="foobar")
    pyramid_request.POST = {"confirm_project_name": "foobar"}
    route_path = mocker.patch.object(pyramid_request, "route_path", autospec=True)
    flash = mocker.spy(pyramid_request.session, "flash")

    confirm_project(project, pyramid_request, fail_route="fail_route")

    route_path.assert_not_called()
    flash.assert_not_called()


def test_confirm_no_input(pyramid_request, mocker):
    project = Project(name="foobar", normalized_name="foobar")
    pyramid_request.POST = {"confirm_project_name": ""}
    route_path = mocker.patch.object(
        pyramid_request, "route_path", autospec=True, return_value="/the-redirect"
    )
    flash = mocker.spy(pyramid_request.session, "flash")

    with pytest.raises(HTTPSeeOther) as err:
        confirm_project(project, pyramid_request, fail_route="fail_route")
    assert err.value.location == "/the-redirect"

    route_path.assert_called_once_with("fail_route", project_name="foobar")
    flash.assert_called_once_with("Confirm the request", queue="error")


def test_confirm_incorrect_input(pyramid_request, mocker):
    project = Project(name="foobar", normalized_name="foobar")
    pyramid_request.POST = {"confirm_project_name": "bizbaz"}
    route_path = mocker.patch.object(
        pyramid_request, "route_path", autospec=True, return_value="/the-redirect"
    )
    flash = mocker.spy(pyramid_request.session, "flash")

    with pytest.raises(HTTPSeeOther) as err:
        confirm_project(project, pyramid_request, fail_route="fail_route")
    assert err.value.location == "/the-redirect"

    route_path.assert_called_once_with("fail_route", project_name="foobar")
    flash.assert_called_once_with(
        "Could not delete project - 'bizbaz' is not the same as 'foobar'",
        queue="error",
    )


def test_confirm_custom_fail_route_params(pyramid_request, mocker):
    """An observation-scoped fail_route gets its own route params, not project_name."""
    project = Project(name="foobar", normalized_name="foobar")
    pyramid_request.POST = {"confirm_project_name": ""}
    route_path = mocker.patch.object(
        pyramid_request, "route_path", autospec=True, return_value="/the-redirect"
    )

    with pytest.raises(HTTPSeeOther) as err:
        confirm_project(
            project, pyramid_request, fail_route="fail_route", observation_id="obs-1"
        )
    assert err.value.location == "/the-redirect"
    route_path.assert_called_once_with("fail_route", observation_id="obs-1")


@pytest.mark.parametrize("flash", [True, False])
def test_quarantine_project(db_request, flash, mocker):
    user = UserFactory.create()
    project = ProjectFactory.create(name="foo")
    RoleFactory.create(user=user, project=project)

    db_request.user = user
    flash_spy = mocker.spy(db_request.session, "flash")

    quarantine_project(project, db_request, flash=flash)

    assert (
        db_request.db.query(Project).filter(Project.name == project.name).count() == 1
    )
    assert (
        db_request.db.query(Project)
        .filter(Project.name == project.name)
        .filter(Project.lifecycle_status == LifecycleStatus.QuarantineEnter)
        .first()
    )
    assert flash_spy.called == flash


@pytest.mark.parametrize("flash", [True, False])
def test_clear_project_quarantine(db_request, flash, mocker):
    user = UserFactory.create()
    project = ProjectFactory.create(
        name="foo", lifecycle_status=LifecycleStatus.QuarantineEnter
    )
    RoleFactory.create(user=user, project=project)

    db_request.user = user
    flash_spy = mocker.spy(db_request.session, "flash")

    clear_project_quarantine(project, db_request, flash=flash)

    assert (
        db_request.db.query(Project).filter(Project.name == project.name).count() == 1
    )
    assert (
        db_request.db.query(Project)
        .filter(Project.name == project.name)
        .filter(Project.lifecycle_status == LifecycleStatus.QuarantineExit)
        .first()
    )
    assert flash_spy.called == flash


def test_deprecate_project(db_request, mocker):
    user = UserFactory.create()
    project = ProjectFactory.create(name="foo")
    RoleFactory.create(user=user, project=project)

    db_request.user = user
    flash_spy = mocker.spy(db_request.session, "flash")

    deprecate_project(project, db_request)

    assert (
        db_request.db.query(Project).filter(Project.name == project.name).count() == 1
    )
    assert (
        db_request.db.query(Project)
        .filter(Project.name == project.name)
        .filter(Project.lifecycle_status == LifecycleStatus.Deprecated)
        .first()
    )
    assert flash_spy.called


def test_deprecate_project_already_archived(db_request, mocker):
    user = UserFactory.create()
    project = ProjectFactory.create(
        name="foo", lifecycle_status=LifecycleStatus.ArchivedNoindex
    )
    RoleFactory.create(user=user, project=project)

    db_request.user = user
    flash_spy = mocker.spy(db_request.session, "flash")

    deprecate_project(project, db_request)

    assert project.lifecycle_status == LifecycleStatus.ArchivedNoindex
    flash_spy.assert_called_once_with(
        "Cannot deprecate project with status archived-noindex", queue="error"
    )


def test_undeprecate_project(db_request, mocker):
    user = UserFactory.create()
    project = ProjectFactory.create(
        name="foo", lifecycle_status=LifecycleStatus.Deprecated
    )
    RoleFactory.create(user=user, project=project)

    db_request.user = user
    flash_spy = mocker.spy(db_request.session, "flash")

    undeprecate_project(project, db_request)

    assert project.lifecycle_status is None
    assert flash_spy.called


def test_undeprecate_project_not_deprecated(db_request, mocker):
    user = UserFactory.create()
    project = ProjectFactory.create(name="foo")
    RoleFactory.create(user=user, project=project)

    db_request.user = user
    flash_spy = mocker.spy(db_request.session, "flash")

    undeprecate_project(project, db_request)

    assert project.lifecycle_status is None
    flash_spy.assert_called_once_with(
        "Can only undeprecate a deprecated project", queue="error"
    )


@pytest.mark.parametrize("flash", [True, False])
def test_quarantine_release(db_request, flash, mocker):
    user = UserFactory.create()
    project = ProjectFactory.create(name="foo")
    release = ReleaseFactory.create(project=project, version="1.0")

    db_request.user = user
    flash_spy = mocker.spy(db_request.session, "flash")

    quarantine_release(release, db_request, flash=flash)

    refreshed = db_request.db.query(Release).filter(Release.id == release.id).one()
    assert refreshed.lifecycle_status == LifecycleStatus.QuarantineEnter
    assert refreshed.lifecycle_status_note == f"Quarantined by {user.username}."

    # A journal entry should be recorded for the release-level action.
    assert (
        db_request.db.query(JournalEntry)
        .filter(JournalEntry.name == project.name)
        .filter(JournalEntry.version == release.version)
        .filter(JournalEntry.action == "release quarantined")
        .count()
        == 1
    )
    # The project itself is not affected.
    assert refreshed.project.lifecycle_status is None
    assert flash_spy.called == flash


@pytest.mark.parametrize("flash", [True, False])
def test_clear_release_quarantine(db_request, flash, mocker):
    user = UserFactory.create()
    project = ProjectFactory.create(name="foo")
    release = ReleaseFactory.create(
        project=project,
        version="1.0",
        lifecycle_status=LifecycleStatus.QuarantineEnter,
    )

    db_request.user = user
    flash_spy = mocker.spy(db_request.session, "flash")

    clear_release_quarantine(release, db_request, flash=flash)

    refreshed = db_request.db.query(Release).filter(Release.id == release.id).one()
    assert refreshed.lifecycle_status == LifecycleStatus.QuarantineExit
    assert (
        db_request.db.query(JournalEntry)
        .filter(JournalEntry.name == project.name)
        .filter(JournalEntry.version == release.version)
        .filter(JournalEntry.action == "release quarantine cleared")
        .count()
        == 1
    )
    assert flash_spy.called == flash


def test_remove_release(db_request, mocker):
    """Removes a release, journals it, emits the event. Does *not* email."""
    user = UserFactory.create()
    project = ProjectFactory.create(name="foo")
    RoleFactory.create(user=user, project=project)
    release = ReleaseFactory.create(project=project, version="1.0")
    other_release = ReleaseFactory.create(project=project, version="1.1")
    record_event = mocker.patch.object(project, "record_event", autospec=True)

    db_request.user = user

    # Contributor notification is the caller's responsibility. The helper
    # mirrors :func:`remove_project`, which never emails.
    send_email = mocker.patch(
        "warehouse.email.send_removed_project_release_email", autospec=True
    )

    remove_release(release, db_request, reason="compromised account")

    # The target release is gone, the sibling release is untouched.
    remaining = db_request.db.query(Release).filter(Release.project == project).all()
    assert [r.version for r in remaining] == [other_release.version]

    entry = (
        db_request.db.query(JournalEntry)
        .options(joinedload(JournalEntry.submitted_by))
        .filter(JournalEntry.action == "remove release")
        .one()
    )
    assert entry.name == project.name
    assert entry.version == "1.0"
    assert entry.submitted_by == user

    record_event.assert_called_once_with(
        tag=EventTag.Project.ReleaseRemove,
        request=db_request,
        additional={
            "submitted_by": user.username,
            "canonical_version": "1",
            "reason": "compromised account",
        },
    )

    send_email.assert_not_called()


@pytest.mark.parametrize("flash", [True, False])
def test_remove_project(db_request, flash, mocker):
    user = UserFactory.create()
    project = ProjectFactory.create(name="foo")
    release = ReleaseFactory.create(project=project)
    FileFactory.create(release=release, filename="who cares")
    RoleFactory.create(user=user, project=project)
    DependencyFactory.create(release=release)

    db_request.user = user
    flash_spy = mocker.spy(db_request.session, "flash")

    remove_project(project, db_request, flash=flash)

    if flash:
        flash_spy.assert_called_once_with("Deleted the project 'foo'", queue="success")
    else:
        flash_spy.assert_not_called()

    assert not (db_request.db.query(Role).filter(Role.project == project).count())
    assert not (
        db_request.db.query(File)
        .join(Release)
        .join(Project)
        .filter(Release.project == project)
        .count()
    )
    assert not (
        db_request.db.query(Dependency)
        .join(Release)
        .filter(Release.project == project)
        .count()
    )
    assert not (db_request.db.query(Release).filter(Release.project == project).count())
    assert not (
        db_request.db.query(Project).filter(Project.name == project.name).count()
    )

    journal_entry = (
        db_request.db.query(JournalEntry)
        .options(joinedload(JournalEntry.submitted_by))
        .filter(JournalEntry.name == "foo")
        .one()
    )
    assert journal_entry.action == "remove project"
    assert journal_entry.submitted_by == db_request.user


@pytest.mark.parametrize("flash", [True, False])
def test_destroy_docs(db_request, flash, mocker):
    user = UserFactory.create()
    project = ProjectFactory.create(name="Foo", has_docs=True)
    RoleFactory.create(user=user, project=project)

    db_request.user = user
    flash_spy = mocker.spy(db_request.session, "flash")
    remove_documentation_recorder = mocker.Mock()
    db_request.task = mocker.Mock(return_value=remove_documentation_recorder)

    destroy_docs(project, db_request, flash=flash)

    assert not (
        db_request.db.query(Project)
        .filter(Project.name == project.name)
        .first()
        .has_docs
    )

    assert remove_documentation_recorder.delay.call_args_list == [
        mocker.call("Foo"),
        mocker.call("foo"),
    ]

    if flash:
        flash_spy.assert_called_once_with(
            "Deleted docs for project 'Foo'", queue="success"
        )
    else:
        flash_spy.assert_not_called()


def test_remove_documentation(db_request, mocker):
    project = ProjectFactory.create(name="foo", has_docs=True)
    task = mocker.sentinel.task
    service = mocker.Mock(spec=["remove_by_prefix"])
    mocker.patch.object(db_request, "find_service", autospec=True, return_value=service)
    log_info = mocker.patch.object(db_request.log, "info")

    remove_documentation(task, db_request, project.name)

    service.remove_by_prefix.assert_called_once_with(f"{project.name}/")
    log_info.assert_called_once_with("Removing documentation for %s", project.name)


def test_remove_documentation_retry(db_request, mocker):
    project = ProjectFactory.create(name="foo", has_docs=True)
    task = mocker.Mock(spec=["retry"])
    service = mocker.Mock(spec=["remove_by_prefix"])
    service.remove_by_prefix.side_effect = Exception
    mocker.patch.object(db_request, "find_service", autospec=True, return_value=service)
    log_info = mocker.patch.object(db_request.log, "info")

    remove_documentation(task, db_request, project.name)

    assert task.retry.call_count == 1
    log_info.assert_called_once_with("Removing documentation for %s", project.name)
