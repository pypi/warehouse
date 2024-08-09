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
