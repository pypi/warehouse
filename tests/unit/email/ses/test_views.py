# SPDX-License-Identifier: Apache-2.0

import json
import uuid

import boto3
import pytest
import requests

from botocore.stub import Stubber
from pyramid.httpexceptions import HTTPBadRequest, HTTPServiceUnavailable

from warehouse.email.ses import views
from warehouse.email.ses.models import EmailMessage, EmailStatuses, Event, EventTypes

from ....common.db.accounts import EmailFactory
from ....common.db.ses import EmailMessageFactory, EventFactory


@pytest.fixture
def verify_sns_message(mocker):
    return mocker.patch.object(views, "_verify_sns_message", autospec=True)


class TestVerifySNSMessageHelper:
    @pytest.fixture
    def message_verifier(self, mocker):
        return mocker.patch.object(views.sns, "MessageVerifier", autospec=True)

    @pytest.fixture
    def sns_request(self, pyramid_request, mocker):
        pyramid_request.http = mocker.sentinel.http
        pyramid_request.registry.settings["mail.topic"] = "this is a topic"
        return pyramid_request

    def test_valid(self, sns_request, message_verifier, mocker):
        views._verify_sns_message(sns_request, mocker.sentinel.message)

        message_verifier.assert_called_once_with(
            topics=["this is a topic"], session=sns_request.http
        )
        message_verifier.return_value.verify.assert_called_once_with(
            mocker.sentinel.message
        )

    def test_invalid(self, sns_request, message_verifier, mocker):
        message_verifier.return_value.verify.side_effect = (
            views.sns.InvalidMessageError("This is an Invalid Message")
        )

        with pytest.raises(HTTPBadRequest, match="This is an Invalid Message"):
            views._verify_sns_message(sns_request, mocker.sentinel.message)

        message_verifier.assert_called_once_with(
            topics=["this is a topic"], session=sns_request.http
        )
        message_verifier.return_value.verify.assert_called_once_with(
            mocker.sentinel.message
        )


class TestConfirmSubscription:
    def test_raises_when_invalid_type(self, pyramid_request):
        pyramid_request.json_body = {"Type": "Notification"}

        with pytest.raises(HTTPBadRequest):
            views.confirm_subscription(pyramid_request)

    def test_confirms(
        self, pyramid_request, pyramid_services, verify_sns_message, mocker
    ):
        data = {
            "Type": "SubscriptionConfirmation",
            "TopicArn": "This is a Topic!",
            "Token": "This is My Token",
        }

        sns_client = boto3.session.Session().client(
            "sns",
            region_name="us-west-2",
            aws_access_key_id="foo",
            aws_secret_access_key="bar",
        )
        aws_session = mocker.create_autospec(boto3.session.Session, instance=True)
        aws_session.client.return_value = sns_client
        pyramid_services.register_service(aws_session, name="aws.session")

        pyramid_request.json_body = data
        pyramid_request.registry.settings["mail.region"] = "us-west-2"

        with Stubber(sns_client) as stubber:
            stubber.add_response(
                "confirm_subscription",
                {},
                {
                    "TopicArn": data["TopicArn"],
                    "Token": data["Token"],
                    "AuthenticateOnUnsubscribe": "true",
                },
            )
            response = views.confirm_subscription(pyramid_request)
            stubber.assert_no_pending_responses()

        assert response.status_code == 200
        verify_sns_message.assert_called_once_with(pyramid_request, data)
        aws_session.client.assert_called_once_with("sns", region_name="us-west-2")


class TestNotification:
    def test_raises_when_invalid_type(self, pyramid_request):
        pyramid_request.json_body = {"Type": "SubscriptionConfirmation"}

        with pytest.raises(HTTPBadRequest):
            views.notification(pyramid_request)

    def test_error_fetching_pubkey(self, pyramid_request, verify_sns_message, metrics):
        verify_sns_message.side_effect = requests.HTTPError

        pyramid_request.json_body = {"Type": "Notification"}

        with pytest.raises(HTTPServiceUnavailable):
            views.notification(pyramid_request)

        metrics.increment.assert_called_once_with("warehouse.ses.sns_verify.error")

    def test_returns_200_existing_event(self, db_request, verify_sns_message):
        event = EventFactory.create()

        db_request.json_body = {"Type": "Notification", "MessageId": event.event_id}

        resp = views.notification(db_request)

        verify_sns_message.assert_called_once_with(db_request, db_request.json_body)
        assert resp.status_code == 200
        assert db_request.db.query(Event).all() == [event]

    def test_returns_400_when_unknown_message(self, db_request, verify_sns_message):
        db_request.json_body = {
            "Type": "Notification",
            "MessageId": str(uuid.uuid4()),
            "Message": json.dumps({"mail": {"messageId": str(uuid.uuid4())}}),
        }

        with pytest.raises(HTTPBadRequest, match="Unknown messageId"):
            views.notification(db_request)

        verify_sns_message.assert_called_once_with(db_request, db_request.json_body)
        assert db_request.db.query(EmailMessage).count() == 0
        assert db_request.db.query(Event).count() == 0

    def test_delivery(self, db_request, verify_sns_message):
        e = EmailFactory.create()
        em = EmailMessageFactory.create(to=e.email)

        event_id = str(uuid.uuid4())
        db_request.json_body = {
            "Type": "Notification",
            "MessageId": event_id,
            "Message": json.dumps(
                {
                    "notificationType": "Delivery",
                    "mail": {"messageId": em.message_id},
                    "delivery": {"someData": "this is some data"},
                }
            ),
        }

        resp = views.notification(db_request)

        verify_sns_message.assert_called_once_with(db_request, db_request.json_body)
        assert resp.status_code == 200

        assert em.status is EmailStatuses.Delivered

        event = db_request.db.query(Event).filter(Event.event_id == event_id).one()

        assert event.email == em
        assert event.event_type is EventTypes.Delivery
        assert event.data == {"someData": "this is some data"}

    def test_bounce(self, db_request, verify_sns_message):
        e = EmailFactory.create()
        em = EmailMessageFactory.create(to=e.email)

        event_id = str(uuid.uuid4())
        db_request.json_body = {
            "Type": "Notification",
            "MessageId": event_id,
            "Message": json.dumps(
                {
                    "notificationType": "Bounce",
                    "mail": {"messageId": em.message_id},
                    "bounce": {
                        "bounceType": "Permanent",
                        "someData": "this is some bounce data",
                    },
                }
            ),
        }

        resp = views.notification(db_request)

        verify_sns_message.assert_called_once_with(db_request, db_request.json_body)
        assert resp.status_code == 200

        assert em.status is EmailStatuses.Bounced

        event = db_request.db.query(Event).filter(Event.event_id == event_id).one()

        assert event.email == em
        assert event.event_type is EventTypes.Bounce
        assert event.data == {
            "bounceType": "Permanent",
            "someData": "this is some bounce data",
        }

    def test_soft_bounce(self, db_request, verify_sns_message):
        e = EmailFactory.create()
        em = EmailMessageFactory.create(to=e.email)

        event_id = str(uuid.uuid4())
        db_request.json_body = {
            "Type": "Notification",
            "MessageId": event_id,
            "Message": json.dumps(
                {
                    "notificationType": "Bounce",
                    "mail": {"messageId": em.message_id},
                    "bounce": {
                        "bounceType": "Transient",
                        "someData": "this is some soft bounce data",
                    },
                }
            ),
        }

        resp = views.notification(db_request)

        verify_sns_message.assert_called_once_with(db_request, db_request.json_body)
        assert resp.status_code == 200

        assert em.status is EmailStatuses.SoftBounced

        event = db_request.db.query(Event).filter(Event.event_id == event_id).one()

        assert event.email == em
        assert event.event_type is EventTypes.Bounce
        assert event.data == {
            "bounceType": "Transient",
            "someData": "this is some soft bounce data",
        }

    def test_soft_bounce_to_deliver(self, db_request, verify_sns_message):
        e = EmailFactory.create()
        em = EmailMessageFactory.create(to=e.email, status=EmailStatuses.SoftBounced)

        event_id = str(uuid.uuid4())
        db_request.json_body = {
            "Type": "Notification",
            "MessageId": event_id,
            "Message": json.dumps(
                {
                    "notificationType": "Delivery",
                    "mail": {"messageId": em.message_id},
                    "delivery": {"someData": "this is some data"},
                }
            ),
        }

        resp = views.notification(db_request)

        verify_sns_message.assert_called_once_with(db_request, db_request.json_body)
        assert resp.status_code == 200

        assert em.status is EmailStatuses.Delivered

        event = db_request.db.query(Event).filter(Event.event_id == event_id).one()

        assert event.email == em
        assert event.event_type is EventTypes.Delivery
        assert event.data == {"someData": "this is some data"}

    def test_spam_complaint(self, db_request, verify_sns_message):
        e = EmailFactory.create()
        em = EmailMessageFactory.create(to=e.email, status=EmailStatuses.Delivered)

        EventFactory.create(email=em, event_type=EventTypes.Delivery)

        event_id = str(uuid.uuid4())
        db_request.json_body = {
            "Type": "Notification",
            "MessageId": event_id,
            "Message": json.dumps(
                {
                    "notificationType": "Complaint",
                    "mail": {"messageId": em.message_id},
                    "complaint": {"someData": "this is some complaint data"},
                }
            ),
        }

        resp = views.notification(db_request)

        verify_sns_message.assert_called_once_with(db_request, db_request.json_body)
        assert resp.status_code == 200

        assert em.status is EmailStatuses.Complained

        event = db_request.db.query(Event).filter(Event.event_id == event_id).one()

        assert event.email == em
        assert event.event_type is EventTypes.Complaint
        assert event.data == {"someData": "this is some complaint data"}

    def test_returns_400_unknown_type(self, db_request, verify_sns_message):
        e = EmailFactory.create()
        em = EmailMessageFactory.create(to=e.email)

        event_id = str(uuid.uuid4())
        db_request.json_body = {
            "Type": "Notification",
            "MessageId": event_id,
            "Message": json.dumps(
                {
                    "notificationType": "Not Really A Type",
                    "mail": {"messageId": em.message_id},
                }
            ),
        }

        with pytest.raises(HTTPBadRequest, match="Unknown notificationType"):
            views.notification(db_request)

        verify_sns_message.assert_called_once_with(db_request, db_request.json_body)
