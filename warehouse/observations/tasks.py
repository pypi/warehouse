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
from __future__ import annotations

import json
import typing

from base64 import b64encode
from textwrap import dedent

from warehouse import db, tasks

from .models import OBSERVATION_KIND_MAP, Observation, ObservationKind

if typing.TYPE_CHECKING:
    from uuid import UUID

    from pyramid.request import Request
    from sqlalchemy.orm import Session as SA_Session

    from warehouse.config import Configurator


@db.listens_for(db.Session, "after_flush")
def new_observation_created(_config, session: SA_Session, _flush_context):
    # Go through each new, changed, and deleted object and attempt to store
    # a cache key that we'll want to purge when the session has been committed.
    for obj in session.new:
        if isinstance(obj, Observation):
            # Add to `session.info` so we can access it in the after_commit listener.
            session.info.setdefault("warehouse.observations.new", set()).add(obj)


@db.listens_for(db.Session, "after_commit")
def execute_observation_report(config: Configurator, session: SA_Session):
    # Fetch the observations from the session.
    observations = session.info.pop("warehouse.observations.new", set())
    for obj in observations:
        # We pass the ID of the Observation, not the Observation itself,
        #  because the Observation object is not currently JSON-serializable.
        config.task(report_observation_to_helpscout).delay(obj.id)


@tasks.task(bind=True, ignore_result=True, acks_late=True)
def report_observation_to_helpscout(task, request: Request, model_id: UUID) -> None:
    """
    Report an Observation to HelpScout for further tracking.

    NOTE: Not using one of the existing `helpscout` libraries,
     because they all seem to be focused on the HelpScout API v1,
     which is deprecated. The v2 API is a bit more complex, but
     we can use the `requests` library directly to make the calls.
     If we see that there's further usage of the HelpScout API,
     we can look at creating a more general-purpose library/module.
    """
    # Fetch the Observation from the database
    model = request.db.query(Observation).get(model_id)

    # TODO: What do we do for Release/File/User/etc?
    #  Maybe need a mapping of ObservationType and the name we want to use.
    target_name = model.related.name

    # Add new Conversation to HelpScout for tracking purposes
    convo_text = dedent(
        f"""
        Kind: {model.kind}
        Summary: {model.summary}
        Model Name: {model.__class__.__name__}

        Project URL: https://pypi.org/project/{target_name}/
        """
    )

    if OBSERVATION_KIND_MAP[model.kind] == ObservationKind.IsMalware:
        convo_text += dedent(
            f"""
            Inspector URL: {model.payload.get("inspector_url")}
            """
        )

    _helpscout_bearer_token = _authenticate_helpscout(request)
    _helpscout_mailbox_id = request.registry.settings.get("helpscout.mailbox_id")

    request_json = {
        "type": "email",
        "customer": {"email": model.observer.parent.email},
        "subject": f"Observation Report for {target_name}",
        "mailboxId": _helpscout_mailbox_id,
        "status": "active",
        "threads": [
            {
                "type": "customer",
                "customer": {"email": model.observer.parent.email},
                "text": convo_text,
            },
        ],
        "tags": ["observation"],
    }

    # if a model has a payload, add it as an attachment.
    if model.payload:
        request_json["threads"][0]["attachments"] = [
            {
                "fileName": f"observation-{target_name}-{model.created}.json",
                "mimeType": "application/json",
                "data": b64encode(json.dumps(model.payload).encode("utf-8")).decode(
                    "utf-8"
                ),
            }
        ]

    resp = request.http.post(
        "https://api.helpscout.net/v2/conversations",
        headers={"Authorization": f"Bearer {_helpscout_bearer_token}"},
        json=request_json,
        timeout=10,
    )
    resp.raise_for_status()


def _authenticate_helpscout(request: Request) -> str:  # pragma: no cover (manual test)
    """
    Perform the authentication dance with HelpScout to get a bearer token.
    https://developer.helpscout.com/mailbox-api/overview/authentication/#client-credentials-flow
    """
    helpscout_app_id = request.registry.settings.get("helpscout.app_id")
    helpscout_app_secret = request.registry.settings.get("helpscout.app_secret")

    auth_token_response = request.http.post(
        "https://api.helpscout.net/v2/oauth2/token",
        auth=(helpscout_app_id, helpscout_app_secret),
        json={"grant_type": "client_credentials"},
        timeout=10,
    )
    auth_token_response.raise_for_status()

    return auth_token_response.json()["access_token"]
