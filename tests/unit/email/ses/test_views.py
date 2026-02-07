# SPDX-License-Identifier: Apache-2.0

import json
import uuid

import pretend
import pytest
import requests

from pyramid.httpexceptions import HTTPBadRequest, HTTPServiceUnavailable

from warehouse.email.ses import views
from warehouse.email.ses.models import EmailMessage, EmailStatuses, Event, EventTypes

from ....common.db.accounts import EmailFactory
from ....common.db.ses import EmailMessageFactory, EventFactory


class TestVerifySNSMessageHelper:
    def test_valid(self, monkeypatch):
        class FakeMessageVerifier:
            @staticmethod
            @pretend.call_recorder
            def __init__(topics, session):
                self.topics = topics
                self.session = session

            @staticmethod
            @pretend.call_recorder
            def verify(message):
                pass

        monkeypatch.setattr(views.sns, "MessageVerifier", FakeMessageVerifier)

        request = pretend.stub(
            http=pretend.stub(),
            registry=pretend.stub(settings={"mail.topic": "this is a topic"}),
        )
        message = pretend.stub()

        views._verify_sns_message(request, message)

        assert FakeMessageVerifier.__init__.calls == [
            pretend.call(topics=["this is a topic"], session=request.http)
        ]
        assert FakeMessageVerifier.verify.calls == [pretend.call(message)]

    def test_invalid(self, monkeypatch):
        class FakeMessageVerifier:
            @staticmethod
            @pretend.call_recorder
            def __init__(topics, session):
                self.topics = topics
                self.session = session

            @staticmethod
            @pretend.call_recorder
            def verify(message):
                raise views.sns.InvalidMessageError("This is an Invalid Message")

        monkeypatch.setattr(views.sns, "MessageVerifier", FakeMessageVerifier)

        request = pretend.stub(
            http=pretend.stub(),
            registry=pretend.stub(settings={"mail.topic": "this is a topic"}),
        )
        message = pretend.stub()

        with pytest.raises(HTTPBadRequest, match="This is an Invalid Message"):
            views._verify_sns_message(request, message)

        assert FakeMessageVerifier.__init__.calls == [
            pretend.call(topics=["this is a topic"], session=request.http)
        ]
        assert FakeMessageVerifier.verify.calls == [pretend.call(message)]


class TestConfirmSubscription:
    def test_raises_when_invalid_type(self):
        request = pretend.stub(json_body={"Type": "Notification"})

        with pytest.raises(HTTPBadRequest):
            views.confirm_subscription(request)

    def test_confirms(self, monkeypatch):
        data = {
            "Type": "SubscriptionConfirmation",
            "TopicArn": "This is a Topic!",
            "Token": "This is My Token",
        }

        aws_client = pretend.stub(
            confirm_subscription=pretend.call_recorder(lambda *a, **kw: None)
        )
        aws_session = pretend.stub(
            client=pretend.call_recorder(lambda c, region_name: aws_client)
        )

        request = pretend.stub(
            json_body=data,
            find_service=lambda name: {"aws.session": aws_session}[name],
            registry=pretend.stub(settings={"mail.region": "us-west-2"}),
        )

        verify_sns_message = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "_verify_sns_message", verify_sns_message)

        response = views.confirm_subscription(request)

        assert response.status_code == 200
        assert verify_sns_message.calls == [pretend.call(request, data)]
        assert aws_session.client.calls == [
            pretend.call("sns", region_name="us-west-2")
        ]
        assert aws_client.confirm_subscription.calls == [
            pretend.call(
                TopicArn=data["TopicArn"],
                Token=data["Token"],
                AuthenticateOnUnsubscribe="true",
            )
        ]


class TestNotification:
    def test_raises_when_invalid_type(self, pyramid_request):
        pyramid_request.json_body = {"Type": "SubscriptionConfirmation"}

        with pytest.raises(HTTPBadRequest):
            views.notification(pyramid_request)

    def test_error_fetching_pubkey(self, pyramid_request, monkeypatch, metrics):
        def raiser(*args, **kwargs):
            raise requests.HTTPError

        monkeypatch.setattr(views, "_verify_sns_message", raiser)

        pyramid_request.json_body = {"Type": "Notification"}

        with pytest.raises(HTTPServiceUnavailable):
            views.notification(pyramid_request)

        assert metrics.increment.calls == [
            pretend.call("warehouse.ses.sns_verify.error")
        ]

    def test_returns_200_existing_event(self, db_request, monkeypatch):
        verify_sns_message = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "_verify_sns_message", verify_sns_message)

        event = EventFactory.create()

        db_request.json_body = {"Type": "Notification", "MessageId": event.event_id}

        resp = views.notification(db_request)

        assert verify_sns_message.calls == [
            pretend.call(db_request, db_request.json_body)
        ]
        assert resp.status_code == 200
        assert db_request.db.query(Event).all() == [event]

    def test_returns_400_when_unknown_message(self, db_request, monkeypatch):
        verify_sns_message = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "_verify_sns_message", verify_sns_message)

        db_request.json_body = {
            "Type": "Notification",
            "MessageId": str(uuid.uuid4()),
            "Message": json.dumps({"mail": {"messageId": str(uuid.uuid4())}}),
        }

        with pytest.raises(HTTPBadRequest, match="Unknown messageId"):
            views.notification(db_request)

        assert verify_sns_message.calls == [
            pretend.call(db_request, db_request.json_body)
        ]
        assert db_request.db.query(EmailMessage).count() == 0
        assert db_request.db.query(Event).count() == 0

    def test_delivery(self, db_request, monkeypatch):
        verify_sns_message = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "_verify_sns_message", verify_sns_message)

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

        assert verify_sns_message.calls == [
            pretend.call(db_request, db_request.json_body)
        ]
        assert resp.status_code == 200

        assert em.status is EmailStatuses.Delivered

        event = db_request.db.query(Event).filter(Event.event_id == event_id).one()

        assert event.email == em
        assert event.event_type is EventTypes.Delivery
        assert event.data == {"someData": "this is some data"}

    def test_bounce(self, db_request, monkeypatch):
        verify_sns_message = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "_verify_sns_message", verify_sns_message)

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

        assert verify_sns_message.calls == [
            pretend.call(db_request, db_request.json_body)
        ]
        assert resp.status_code == 200

        assert em.status is EmailStatuses.Bounced

        event = db_request.db.query(Event).filter(Event.event_id == event_id).one()

        assert event.email == em
        assert event.event_type is EventTypes.Bounce
        assert event.data == {
            "bounceType": "Permanent",
            "someData": "this is some bounce data",
        }

    def test_soft_bounce(self, db_request, monkeypatch):
        verify_sns_message = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "_verify_sns_message", verify_sns_message)

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

        assert verify_sns_message.calls == [
            pretend.call(db_request, db_request.json_body)
        ]
        assert resp.status_code == 200

        assert em.status is EmailStatuses.SoftBounced

        event = db_request.db.query(Event).filter(Event.event_id == event_id).one()

        assert event.email == em
        assert event.event_type is EventTypes.Bounce
        assert event.data == {
            "bounceType": "Transient",
            "someData": "this is some soft bounce data",
        }

    def test_soft_bounce_to_deliver(self, db_request, monkeypatch):
        verify_sns_message = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "_verify_sns_message", verify_sns_message)

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

        assert verify_sns_message.calls == [
            pretend.call(db_request, db_request.json_body)
        ]
        assert resp.status_code == 200

        assert em.status is EmailStatuses.Delivered

        event = db_request.db.query(Event).filter(Event.event_id == event_id).one()

        assert event.email == em
        assert event.event_type is EventTypes.Delivery
        assert event.data == {"someData": "this is some data"}

    def test_spam_complaint(self, db_request, monkeypatch):
        verify_sns_message = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "_verify_sns_message", verify_sns_message)

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

        assert verify_sns_message.calls == [
            pretend.call(db_request, db_request.json_body)
        ]
        assert resp.status_code == 200

        assert em.status is EmailStatuses.Complained

        event = db_request.db.query(Event).filter(Event.event_id == event_id).one()

        assert event.email == em
        assert event.event_type is EventTypes.Complaint
        assert event.data == {"someData": "this is some complaint data"}

    def test_returns_400_unknown_type(self, db_request, monkeypatch):
        verify_sns_message = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(views, "_verify_sns_message", verify_sns_message)

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

        assert verify_sns_message.calls == [
            pretend.call(db_request, db_request.json_body)
        ]
