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

import pretend
import pytest
import requests
import responses

from warehouse.observations.models import ObservationKind
from warehouse.observations.tasks import (
    execute_observation_report,
    report_observation_to_helpscout,
)

from ...common.db.accounts import UserFactory
from ...common.db.packaging import ProjectFactory


def test_execute_observation_report(app_config):
    _delay = pretend.call_recorder(lambda x: None)
    app_config.task = lambda x: pretend.stub(delay=_delay)
    observation = pretend.stub(id=pretend.stub())
    session = pretend.stub(info={"warehouse.observations.new": {observation}})

    execute_observation_report(app_config, session)

    assert _delay.calls == [pretend.call(observation.id)]


@responses.activate
@pytest.mark.parametrize(
    "kind", [ObservationKind.IsMalware, ObservationKind.SomethingElse]
)
@pytest.mark.parametrize("payload", [{}, {"foo": "bar"}])
def test_report_observation_to_helpscout(kind, payload, db_request, monkeypatch):
    db_request.registry.settings = {"helpscout.app_secret": "fake-sekret"}
    # Mock out the authentication to HelpScout
    monkeypatch.setattr(
        "warehouse.observations.tasks._authenticate_helpscout",
        lambda x: "SOME_TOKEN",
    )

    # Create an Observation
    user = UserFactory.create()
    db_request.user = user
    project = ProjectFactory.create()
    observation = project.record_observation(
        request=db_request,
        kind=kind,
        summary="Project Observation",
        payload=payload,
        actor=user,
    )
    # Need to flush the session to ensure the Observation has an ID
    db_request.db.flush()

    db_request.http = requests.Session()

    responses.add(
        responses.POST,
        "https://api.helpscout.net/v2/conversations",
        json={"id": 123},
        headers={"Location": "https://api.helpscout.net/v2/conversations/123"},
    )

    report_observation_to_helpscout(None, db_request, observation.id)

    assert len(responses.calls) == 1
    assert (
        responses.calls[0].request.url == "https://api.helpscout.net/v2/conversations"
    )
    assert (
        observation.additional["helpscout_conversation_url"]
        == "https://api.helpscout.net/v2/conversations/123"
    )
