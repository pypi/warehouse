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
from warehouse.helpdesk.interfaces import IHelpDeskService

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


@tasks.task(
    bind=True,
    ignore_result=True,
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def report_observation_to_helpscout(task, request: Request, model_id: UUID) -> None:
    """
    Report an Observation to HelpScout for further tracking.
    """
    # Fetch the Observation from the database
    model = request.db.get(Observation, model_id)

    # Check to see if this ObservationKind should be sent
    if OBSERVATION_KIND_MAP[model.kind] not in [
        ObservationKind.IsDependencyConfusion,
        ObservationKind.IsMalware,
    ]:
        return

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

            Malware Reports URL: {request.route_url(
                "admin.malware_reports.project.list",
                project_name=target_name,
                _host=request.registry.settings.get("warehouse.domain"),
            )}
            """
        )

    helpdesk_service = request.find_service(IHelpDeskService)

    request_json = {
        "type": "email",
        "customer": {"email": model.observer.parent.email},
        "subject": f"Observation Report for {target_name}",
        "mailboxId": helpdesk_service.mailbox_id,
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

    new_convo_location = helpdesk_service.create_conversation(request_json=request_json)

    # Add the conversation URL back to the Observation for tracking purposes.
    model.additional["helpscout_conversation_url"] = new_convo_location
    request.db.add(model)
    return
