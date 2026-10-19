# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
from uuid import UUID

from warehouse.observations.models import ObservationKind

from ...common.db.accounts import UserFactory
from ...common.db.observations import ObserverFactory
from ...common.db.packaging import ProjectFactory, ReleaseFactory


def test_observer(db_session):
    observer = ObserverFactory.create()

    assert isinstance(observer.id, UUID)
    assert isinstance(observer.created, datetime)
    assert observer.parent is None


def test_user_observer_relationship(db_session):
    observer = ObserverFactory.create()
    user = UserFactory.create(observer=observer)

    assert user.observer == observer
    assert observer.parent == user


def test_observer_observations_relationship(db_request):
    user = UserFactory.create()
    db_request.user = user
    project = ProjectFactory.create()

    project.record_observation(
        request=db_request,
        kind=ObservationKind.SomethingElse,
        summary="Project Observation",
        payload={},
        actor=user,
    )

    assert len(project.observations) == 1
    observation = project.observations[0]
    assert observation.observer.parent == user
    assert str(observation) == "<ProjectObservation something_else>"
    assert observation.kind_display == "Something Else"


def test_project_observations_newest_first(db_request):
    """`HasObservations.observations` returns rows newest-first."""
    user = UserFactory.create()
    db_request.user = user
    project = ProjectFactory.create()

    older = project.record_observation(
        request=db_request,
        kind=ObservationKind.SomethingElse,
        summary="Older Observation",
        payload={},
        actor=user,
    )
    older.created = datetime(2026, 1, 1)
    newer = project.record_observation(
        request=db_request,
        kind=ObservationKind.SomethingElse,
        summary="Newer Observation",
        payload={},
        actor=user,
    )
    newer.created = datetime(2026, 1, 2)

    db_request.db.flush()
    db_request.db.expire_all()

    assert [o.summary for o in project.observations] == [
        "Newer Observation",
        "Older Observation",
    ]


def test_observer_created_from_user_when_observation_made(db_request):
    user = UserFactory.create()
    db_request.user = user
    project = ProjectFactory.create()

    project.record_observation(
        request=db_request,
        kind=ObservationKind.SomethingElse,
        summary="Project Observation",
        payload={},
        actor=user,
    )

    assert len(project.observations) == 1
    observation = project.observations[0]
    assert observation.observer.parent == user
    assert str(observation) == "<ProjectObservation something_else>"


def test_user_observations_relationship(db_request):
    user = UserFactory.create()
    db_request.user = user
    project = ProjectFactory.create()
    release = ReleaseFactory.create(project=project)

    project.record_observation(
        request=db_request,
        kind=ObservationKind.SomethingElse,
        summary="Project Observation",
        payload={},
        actor=user,
    )
    release.record_observation(
        request=db_request,
        kind=ObservationKind.SomethingElse,
        summary="Release Observation",
        payload={},
        actor=user,
    )

    db_request.db.flush()  # so Observer is created

    assert len(user.observer.observations) == 2


def test_observer_observations_newest_first(db_request):
    """`Observer.observations` returns rows newest-first."""
    user = UserFactory.create()
    db_request.user = user
    project = ProjectFactory.create()
    release = ReleaseFactory.create(project=project)

    older = project.record_observation(
        request=db_request,
        kind=ObservationKind.SomethingElse,
        summary="Project Observation",
        payload={},
        actor=user,
    )
    older.created = datetime(2026, 1, 1)
    newer = release.record_observation(
        request=db_request,
        kind=ObservationKind.SomethingElse,
        summary="Release Observation",
        payload={},
        actor=user,
    )
    newer.created = datetime(2026, 1, 2)

    db_request.db.flush()
    db_request.db.expire_all()

    assert [o.summary for o in user.observer.observations] == [
        "Release Observation",
        "Project Observation",
    ]
