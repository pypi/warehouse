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

import json

from pyramid.response import Response
from pyramid.view import view_config
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.sql import exists

from warehouse.email.ses.models import EmailMessage, EmailStatus, Event


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
        raise None  # 400 Error pls

    sns_client = request.find_service(name="aws.session").client("sns", region_name="us-west-2")
    sns_client.confirm_subscription(
        TopicArn=data["TopicArn"],
        Token=data["Token"],
        AuthenticateOnUnsubscribe='true',
    )

    return Response()


@view_config(
    route_name="ses.hook",
    require_methods=["POST"],
    require_csrf=False,
    header="x-amz-sns-message-type:Notification",
)
def notification(request):
    data = request.json_body

    print(data)

    # Check to ensure that the Type is what we expect.
    if data.get("Type") != "Notification":
        raise None  # 400 Error pls

    event_exists = (
        request.db.query(exists().where(Event.event_id == data["MessageId"]))
                  .scalar())
    if event_exists:
        return Response()

    message = json.loads(data["Message"])
    message_id = message["mail"]["messageId"]

    try:
        email = (
            request.db.query(EmailMessage)
                      .filter(EmailMessage.message_id == message_id)
                      .one())
    except NoResultFound:
        raise None  # 404?

    # Load our state machine from the status in the database, process any
    # transition we have from this event, and then save the result.
    machine = EmailStatus.load(request.db, email.status)
    if message["notificationType"] == "Delivery":
        machine.deliver(email.to)
    elif (message["notificationType"] == "Bounce" and
            message["bounce"]["bounceType"] == "Permanent"):
        machine.bounce(email.to)
    elif message["notificationType"] == "Bounce":
        machine.soft_bounce(email.to)
    elif message["notificationType"] == "Complaint":
        machine.complain(email.to)
    email.status = machine.save()

    # Save our event to the database.
    request.db.add(
        Event(
            email=email,
            event_id=data["MessageId"],
            event_type=message["notificationType"],
            data=message[message["notificationType"].lower()],
        )
    )

    return Response()
