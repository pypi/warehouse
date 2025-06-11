# SPDX-License-Identifier: Apache-2.0

import json

import requests

from pyramid.httpexceptions import HTTPBadRequest, HTTPOk, HTTPServiceUnavailable
from pyramid.view import view_config
from sqlalchemy.exc import NoResultFound
from sqlalchemy.sql import exists

from warehouse.email.ses.models import EmailMessage, EmailStatus, Event, EventTypes
from warehouse.metrics import IMetricsService
from warehouse.utils import sns


def _verify_sns_message(request, message):
    verifier = sns.MessageVerifier(
        topics=[request.registry.settings["mail.topic"]], session=request.http
    )

    try:
        verifier.verify(message)
    except sns.InvalidMessageError as exc:
        raise HTTPBadRequest(str(exc)) from None


@view_config(
    route_name="ses.hook",
    require_methods=["POST"],
    require_csrf=False,
    header="x-amz-sns-message-type:SubscriptionConfirmation",
)
def confirm_subscription(request):
    data = request.json_body

    # Check to ensure that the Type is what we expect.
    if data.get("Type") != "SubscriptionConfirmation":
        raise HTTPBadRequest("Expected Type of SubscriptionConfirmation")

    _verify_sns_message(request, data)

    aws_session = request.find_service(name="aws.session")
    sns_client = aws_session.client(
        "sns", region_name=request.registry.settings.get("mail.region")
    )

    sns_client.confirm_subscription(
        TopicArn=data["TopicArn"], Token=data["Token"], AuthenticateOnUnsubscribe="true"
    )

    return HTTPOk()


@view_config(
    route_name="ses.hook",
    require_methods=["POST"],
    require_csrf=False,
    header="x-amz-sns-message-type:Notification",
)
def notification(request):
    metrics = request.find_service(IMetricsService, context=None)
    data = request.json_body

    # Check to ensure that the Type is what we expect.
    if data.get("Type") != "Notification":
        raise HTTPBadRequest("Expected Type of Notification")

    try:
        _verify_sns_message(request, data)
    except requests.HTTPError:
        metrics.increment("warehouse.ses.sns_verify.error")
        raise HTTPServiceUnavailable from None

    event_exists = request.db.query(
        exists().where(Event.event_id == data["MessageId"])
    ).scalar()
    if event_exists:
        return HTTPOk()

    message = json.loads(data["Message"])
    message_id = message["mail"]["messageId"]

    try:
        email = (
            request.db.query(EmailMessage)
            .filter(EmailMessage.message_id == message_id)
            .one()
        )
    except NoResultFound:
        raise HTTPBadRequest("Unknown messageId")

    # Load our state machine from the status in the database, process any
    # transition we have from this event, and then save the result.
    machine = EmailStatus.load(email)
    if message["notificationType"] == "Delivery":
        machine.deliver()
    elif (
        message["notificationType"] == "Bounce"
        and message["bounce"]["bounceType"] == "Permanent"
    ):
        machine.bounce()
    elif message["notificationType"] == "Bounce":
        machine.soft_bounce()
    elif message["notificationType"] == "Complaint":
        machine.complain()
    else:
        raise HTTPBadRequest("Unknown notificationType")
    email = machine.save()

    # Save our event to the database.
    request.db.add(
        Event(
            email=email,
            event_id=data["MessageId"],
            event_type=EventTypes(message["notificationType"]),
            data=message[message["notificationType"].lower()],
        )
    )

    return HTTPOk()
