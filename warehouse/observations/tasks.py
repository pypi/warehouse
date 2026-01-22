# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import typing

from base64 import b64encode
from datetime import datetime, timedelta, timezone
from textwrap import dedent

from humanize import naturaldate, naturaltime
from requests.exceptions import RequestException

from warehouse import db, tasks
from warehouse.helpdesk.interfaces import IAdminNotificationService, IHelpDeskService
from warehouse.packaging.models import LifecycleStatus
from warehouse.utils.project import quarantine_project

from .models import OBSERVATION_KIND_MAP, Observation, ObservationKind

if typing.TYPE_CHECKING:
    from uuid import UUID

    from pyramid.request import Request
    from sqlalchemy.orm import Session as SA_Session

    from warehouse.config import Configurator
    from warehouse.tasks import WarehouseTask


@db.listens_for(db.Session, "after_flush")
def new_observation_created(_config, session: SA_Session, _flush_context):
    # Go through each new, changed, and deleted object and attempt to store
    # a cache key that we'll want to purge when the session has been committed.
    for obj in session.new:
        if isinstance(obj, Observation):
            # Add to `session.info` so we can access it in the after_commit listener.
            session.info.setdefault("warehouse.observations.new", set()).add(obj)


@db.listens_for(db.Session, "after_commit")
def react_to_observation_created(config: Configurator, session: SA_Session):
    # Fetch the observations from the session.
    observations = session.info.pop("warehouse.observations.new", set())
    for obj in observations:
        # We pass the ID of the Observation, not the Observation itself,
        #  because the Observation object is not currently JSON-serializable.
        config.task(report_observation_to_helpscout).delay(obj.id)
        # Now that we've told Help Scout, run auto-quarantine.
        config.task(evaluate_project_for_quarantine).delay(obj.id)


@tasks.task(
    bind=True,
    ignore_result=True,
    acks_late=True,
    autoretry_for=(RequestException,),
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

    warehouse_domain = request.registry.settings.get("warehouse.domain")

    # Add new Conversation to HelpScout for tracking purposes
    convo_text = dedent(
        f"""
        Kind: {model.kind}
        Summary: {model.summary}
        Model Name: {model.__class__.__name__}

        Project URL: {request.route_url(
            'packaging.project', name=target_name, _host=warehouse_domain
        )}
        """
    )
    for owner in model.related.owners:
        username = owner.username
        owner_url = request.route_url(
            "admin.user.detail", username=username, _host=warehouse_domain
        )
        convo_text += f"Owner: {username}\n"
        convo_text += f"Owner URL: {owner_url}\n"

    if OBSERVATION_KIND_MAP[model.kind] == ObservationKind.IsMalware:
        convo_text += dedent(
            f"""
            Inspector URL: {model.payload.get("inspector_url")}

            Malware Reports URL: {request.route_url(
                "admin.malware_reports.project.list",
                project_name=target_name,
                _host=warehouse_domain,
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


@tasks.task(
    bind=True,
    ignore_result=True,
    acks_late=True,
    autoretry_for=(RequestException,),
    retry_backoff=True,
)
def evaluate_project_for_quarantine(
    task: WarehouseTask, request: Request, observation_id: UUID
) -> None:
    """
    Conditionally quarantine a Project for Admin review.

    Conditions must be met:

    - ObservationKind is IsMalware
    - Observed Project is not already quarantined
    - EITHER:
      - Trusted observer (`User.is_observer`) reports a young project (<24h old)
      - OR: Project has at least 2 Observations, at least 1 by `User.is_observer`
    """
    # Fetch the Observation from the database, load the related Project
    observation = request.db.get(Observation, observation_id)
    project = observation.related

    # Add more logging context
    logger = request.log.bind(
        kind=observation.kind,
        observer=observation.observer.parent.username,
        project=project.name,
        task=task.name,
    )

    # Check to see if this ObservationKind should be sent
    if OBSERVATION_KIND_MAP[observation.kind] != ObservationKind.IsMalware:
        logger.info("ObservationKind is not IsMalware. Not quarantining.")
        return
    # Check if the project is already quarantined
    if project.lifecycle_status == LifecycleStatus.QuarantineEnter:
        logger.info("Project is already quarantined. No change needed.")
        return

    # Fast-track: Trusted observer reporting a young project (< 24 hours old)
    # A single trusted observer is sufficient for very new projects
    reporter = observation.observer.parent
    # Note: project.created is a naive UTC datetime from the database
    project_is_young = project.created is not None and (
        datetime.now(timezone.utc) - project.created.replace(tzinfo=timezone.utc)
    ) < timedelta(hours=24)
    if reporter.is_observer and project_is_young:
        logger.info(
            "Auto-quarantining young project (<24h) reported by trusted observer."
        )
    else:
        # Corroboration required: 2+ observers, at least 1 trusted
        observer_users = {obs.observer.parent for obs in project.observations}
        if len(observer_users) < 2:
            logger.info("Project has fewer than 2 observers. Not quarantining.")
            return
        if not any(observer.is_observer for observer in observer_users):
            logger.info(
                "Project has no `User.is_observer` Observers. Not quarantining."
            )
            return
        logger.info("Auto-quarantining project due to multiple malware observations.")

    # Call a Slack Webhook to notify admins of the quarantine
    warehouse_domain = request.registry.settings.get("warehouse.domain")

    project_page = request.route_url(
        "packaging.project",
        name=project.normalized_name,
        _host=warehouse_domain,
    )
    last_published_date = naturaldate(project.latest_version.created)
    last_published_time = naturaltime(project.latest_version.created)
    first_published_date = naturaldate(project.created)
    first_published_time = naturaltime(project.created)
    malware_reports_url = request.route_url(
        "admin.malware_reports.project.list",
        project_name=project.normalized_name,
        _host=warehouse_domain,
    )

    # Construct a Slack webhook payload with the project details
    notification_service = request.find_service(IAdminNotificationService)
    webhook_payload = {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Auto-Quarantine: <{project_page}|{project.name}>*",
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"*Last Published:*\n"
                            f"{last_published_date} ({last_published_time})"
                        ),
                    },
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"*First Published:*\n"
                            f"{first_published_date} ({first_published_time})"
                        ),
                    },
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"Visit <{malware_reports_url}|"
                        f"PyPI Admin :dumpster-fire: Malware Reports> "
                        f"to review and take action"
                    ),
                },
            },
            {"type": "divider"},
        ]
    }

    # Quarantine the project
    quarantine_project(project, request, flash=False)

    # Send the notification
    notification_service.send_notification(payload=webhook_payload)

    return
