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

import uuid

import pretend
import pytest

from pyramid_mailer.mailer import DummyMailer
from zope.interface.verify import verifyClass

from warehouse.email.interfaces import IEmailSender
from warehouse.email.services import (
    SMTPEmailSender, SESEmailSender, _format_sender,
)
from warehouse.email.ses.models import EmailMessage


@pytest.mark.parametrize(
    ("sitename", "sender", "expected"),
    [
        (
            "My Site Name",
            "noreply@example.com",
            "My Site Name <noreply@example.com>",
        ),
        ("My Site Name", None, None),
    ],
)
def test_format_sender(sitename, sender, expected):
    assert _format_sender(sitename, sender) == expected


class TestSMTPEmailSender:

    def test_verify_service(self):
        assert verifyClass(IEmailSender, SMTPEmailSender)

    def test_creates_service(self):
        mailer = pretend.stub()
        context = pretend.stub()
        request = pretend.stub(
            registry=pretend.stub(
                settings={
                    "site.name": "DevPyPI",
                    "mail.sender": "noreply@example.com",
                },
                getUtility=lambda mailr: mailer,
            )
        )

        service = SMTPEmailSender.create_service(context, request)

        assert isinstance(service, SMTPEmailSender)
        assert service.mailer is mailer
        assert service.sender == "DevPyPI <noreply@example.com>"

    def test_send(self):
        mailer = DummyMailer()
        service = SMTPEmailSender(mailer,
                                  sender="DevPyPI <noreply@example.com>")

        service.send("a subject", "a body", recipient="sombody@example.com")

        assert len(mailer.outbox) == 1

        msg = mailer.outbox[0]

        assert msg.subject == "a subject"
        assert msg.body == "a body"
        assert msg.recipients == ["sombody@example.com"]
        assert msg.sender == "DevPyPI <noreply@example.com>"


class TestSESEmailSender:

    def test_verify_service(self):
        assert verifyClass(IEmailSender, SESEmailSender)

    def test_creates_service(self):
        aws_client = pretend.stub()
        aws_session = pretend.stub(
            client=pretend.call_recorder(lambda name, region_name: aws_client),
        )
        request = pretend.stub(
            find_service=lambda name: {"aws.session": aws_session}[name],
            registry=pretend.stub(
                settings={
                    "site.name": "DevPyPI",
                    "mail.region": "us-west-2",
                    "mail.sender": "noreply@example.com",
                },
            ),
            db=pretend.stub(),
        )

        sender = SESEmailSender.create_service(pretend.stub(), request)

        assert aws_session.client.calls == [
            pretend.call("ses", region_name="us-west-2"),
        ]

        assert sender._client is aws_client
        assert sender._sender == "DevPyPI <noreply@example.com>"
        assert sender._db is request.db

    def test_send(self, db_session):
        resp = {"MessageId": str(uuid.uuid4()) + "-ses"}
        aws_client = pretend.stub(
            send_email=pretend.call_recorder(lambda *a, **kw: resp),
        )
        sender = SESEmailSender(aws_client,
                                sender="DevPyPI <noreply@example.com>",
                                db=db_session)

        sender.send(
            "This is a Subject",
            "This is a Body",
            recipient="FooBar <somebody@example.com>",
        )

        assert aws_client.send_email.calls == [
            pretend.call(
                Source="DevPyPI <noreply@example.com>",
                Destination={"ToAddresses": ["FooBar <somebody@example.com>"]},
                Message={
                    "Subject": {
                        "Data": "This is a Subject",
                        "Charset": "UTF-8",
                    },
                    "Body": {
                        "Text": {"Data": "This is a Body", "Charset": "UTF-8"},
                    },
                },
            ),
        ]

        em = (db_session.query(EmailMessage)
                        .filter_by(message_id=resp["MessageId"])
                        .one())

        assert em.from_ == "noreply@example.com"
        assert em.to == "somebody@example.com"
        assert em.subject == "This is a Subject"
