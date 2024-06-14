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

from jinja2.exceptions import TemplateNotFound
from pyramid_mailer.mailer import DummyMailer
from zope.interface.verify import verifyClass

from warehouse.email import services as email_services
from warehouse.email.interfaces import IEmailSender
from warehouse.email.services import (
    ConsoleAndSMTPEmailSender,
    EmailMessage,
    SESEmailSender,
    SMTPEmailSender,
    _format_sender,
)
from warehouse.email.ses.models import EmailMessage as SESEmailMessage


@pytest.mark.parametrize(
    ("sitename", "sender", "expected"),
    [
        ("My Site Name", "noreply@example.com", "My Site Name <noreply@example.com>"),
        ("My Site Name", None, None),
    ],
)
def test_format_sender(sitename, sender, expected):
    assert _format_sender(sitename, sender) == expected


class TestEmailMessage:
    def test_renders_plaintext(self, pyramid_config, pyramid_request, monkeypatch):
        real_render = email_services.render

        def render(template, *args, **kwargs):
            if template.endswith(".html"):
                raise TemplateNotFound(template)
            return real_render(template, *args, **kwargs)

        monkeypatch.setattr(email_services, "render", render)

        subject_renderer = pyramid_config.testing_add_renderer("email/foo/subject.txt")
        subject_renderer.string_response = "Email Subject"

        body_renderer = pyramid_config.testing_add_renderer("email/foo/body.txt")
        body_renderer.string_response = "Email Body"

        msg = EmailMessage.from_template(
            "foo", {"my_var": "my value"}, request=pyramid_request
        )

        subject_renderer.assert_(my_var="my value")
        body_renderer.assert_(my_var="my value")

        assert msg.subject == "Email Subject"
        assert msg.body_text == "Email Body"
        assert msg.body_html is None

    def test_renders_html(self, pyramid_config, pyramid_request):
        subject_renderer = pyramid_config.testing_add_renderer("email/foo/subject.txt")
        subject_renderer.string_response = "Email Subject"

        body_renderer = pyramid_config.testing_add_renderer("email/foo/body.txt")
        body_renderer.string_response = "Email Body"

        html_renderer = pyramid_config.testing_add_renderer("email/foo/body.html")
        html_renderer.string_response = "<p>Email HTML Body</p>"

        msg = EmailMessage.from_template(
            "foo", {"my_var": "my value"}, request=pyramid_request
        )

        subject_renderer.assert_(my_var="my value")
        body_renderer.assert_(my_var="my value")
        html_renderer.assert_(my_var="my value")

        assert msg.subject == "Email Subject"
        assert msg.body_text == "Email Body"
        assert msg.body_html == (
            "<html>\n<head></head>\n<body><p>Email HTML Body</p></body>\n</html>\n"
        )

    def test_strips_newlines_from_subject(self, pyramid_config, pyramid_request):
        subject_renderer = pyramid_config.testing_add_renderer("email/foo/subject.txt")
        subject_renderer.string_response = "Email Subject\n"

        body_renderer = pyramid_config.testing_add_renderer("email/foo/body.txt")
        body_renderer.string_response = "Email Body"

        html_renderer = pyramid_config.testing_add_renderer("email/foo/body.html")
        html_renderer.string_response = "<p>Email HTML Body</p>"

        msg = EmailMessage.from_template(
            "foo", {"my_var": "my value"}, request=pyramid_request
        )

        subject_renderer.assert_(my_var="my value")

        assert msg.subject == "Email Subject"


@pytest.mark.parametrize("sender_class", [SMTPEmailSender, ConsoleAndSMTPEmailSender])
class TestSMTPEmailSender:
    def test_verify_service(self, sender_class):
        assert verifyClass(IEmailSender, sender_class)

    def test_creates_service(self, sender_class):
        mailer = pretend.stub()
        context = pretend.stub()
        request = pretend.stub(
            registry=pretend.stub(
                settings={"site.name": "DevPyPI", "mail.sender": "noreply@example.com"},
                getUtility=lambda mailr: mailer,
            )
        )

        service = sender_class.create_service(context, request)

        assert isinstance(service, sender_class)
        assert service.mailer is mailer
        assert service.sender == "DevPyPI <noreply@example.com>"

    def test_send(self, sender_class):
        mailer = DummyMailer()
        service = sender_class(mailer, sender="DevPyPI <noreply@example.com>")

        service.send(
            "sombody@example.com",
            EmailMessage(
                subject="a subject", body_text="a body", body_html="a html body"
            ),
        )

        assert len(mailer.outbox) == 1

        msg = mailer.outbox[0]

        assert msg.subject == "a subject"
        assert msg.body == "a body"
        assert msg.html == "a html body"
        assert msg.recipients == ["sombody@example.com"]
        assert msg.sender == "DevPyPI <noreply@example.com>"

    def test_last_sent(self, sender_class):
        mailer = DummyMailer()
        service = sender_class(mailer, sender="DevPyPI <noreply@example.com>")

        assert service.last_sent(to=pretend.stub(), subject=pretend.stub) is None


class TestConsoleAndSMTPEmailSender:
    def test_send(self, capsys):
        mailer = DummyMailer()
        service = ConsoleAndSMTPEmailSender(
            mailer, sender="DevPyPI <noreply@example.com>"
        )

        service.send(
            "sombody@example.com",
            EmailMessage(
                subject="a subject", body_text="a body", body_html="a html body"
            ),
        )
        captured = capsys.readouterr()
        expected = """
Email sent
Subject: a subject
From: DevPyPI <noreply@example.com>
To: sombody@example.com
HTML: Visualize at http://localhost:1080
Text: a body"""
        assert captured.out.strip() == expected.strip()


class TestSESEmailSender:
    def test_verify_service(self):
        assert verifyClass(IEmailSender, SESEmailSender)

    def test_creates_service(self):
        aws_client = pretend.stub()
        aws_session = pretend.stub(
            client=pretend.call_recorder(lambda name, region_name: aws_client)
        )
        request = pretend.stub(
            find_service=lambda name: {"aws.session": aws_session}[name],
            registry=pretend.stub(
                settings={
                    "site.name": "DevPyPI",
                    "mail.region": "us-west-2",
                    "mail.sender": "noreply@example.com",
                }
            ),
            db=pretend.stub(),
        )

        sender = SESEmailSender.create_service(pretend.stub(), request)

        assert aws_session.client.calls == [
            pretend.call("ses", region_name="us-west-2")
        ]

        assert sender._client is aws_client
        assert sender._sender == "DevPyPI <noreply@example.com>"
        assert sender._db is request.db

    def test_send_with_plaintext(self, db_session):
        resp = {"MessageId": str(uuid.uuid4()) + "-ses"}
        aws_client = pretend.stub(
            send_raw_email=pretend.call_recorder(lambda *a, **kw: resp)
        )
        sender = SESEmailSender(
            aws_client, sender="DevPyPI <noreply@example.com>", db=db_session
        )

        sender.send(
            "Foobar <somebody@example.com>",
            EmailMessage(
                subject="This is a Subject", body_text="This is a plain text body"
            ),
        )

        assert aws_client.send_raw_email.calls == [
            pretend.call(
                Source="DevPyPI <noreply@example.com>",
                Destinations=["Foobar <somebody@example.com>"],
                RawMessage={
                    "Data": (
                        b"Subject: This is a Subject\n"
                        b"From: DevPyPI <noreply@example.com>\n"
                        b"To: Foobar <somebody@example.com>\n"
                        b'Content-Type: text/plain; charset="utf-8"\n'
                        b"Content-Transfer-Encoding: 7bit\n"
                        b"MIME-Version: 1.0\n"
                        b"\n"
                        b"This is a plain text body\n"
                    )
                },
            )
        ]

        em = (
            db_session.query(SESEmailMessage)
            .filter_by(message_id=resp["MessageId"])
            .one()
        )

        assert em.from_ == "noreply@example.com"
        assert em.to == "somebody@example.com"
        assert em.subject == "This is a Subject"

    def test_send_with_unicode_and_html(self, db_session):
        # Determine what the random boundary token will be
        import random
        import sys

        random.seed(42)
        token = random.randrange(sys.maxsize)
        random.seed(42)

        resp = {"MessageId": str(uuid.uuid4()) + "-ses"}
        aws_client = pretend.stub(
            send_raw_email=pretend.call_recorder(lambda *a, **kw: resp)
        )
        sender = SESEmailSender(
            aws_client, sender="DevPyPI <noreply@example.com>", db=db_session
        )

        sender.send(
            "Fööbar <somebody@example.com>",
            EmailMessage(
                subject="This is a Subject",
                body_text="This is a plain text body",
                body_html="<p>This is a html body! 💩</p>",
            ),
        )

        assert aws_client.send_raw_email.calls == [
            pretend.call(
                Source="DevPyPI <noreply@example.com>",
                Destinations=["Fööbar <somebody@example.com>"],
                RawMessage={
                    "Data": (
                        b"Subject: This is a Subject\n"
                        b"From: DevPyPI <noreply@example.com>\n"
                        b"To: =?utf-8?q?F=C3=B6=C3=B6bar?= <somebody@example.com>\n"
                        b"MIME-Version: 1.0\n"
                        b"Content-Type: multipart/alternative;\n"
                        b' boundary="===============%(token)d=="\n'
                        b"\n"
                        b"--===============%(token)d==\n"
                        b'Content-Type: text/plain; charset="utf-8"\n'
                        b"Content-Transfer-Encoding: 7bit\n"
                        b"\n"
                        b"This is a plain text body\n"
                        b"\n"
                        b"--===============%(token)d==\n"
                        b'Content-Type: text/html; charset="utf-8"\n'
                        b"Content-Transfer-Encoding: 8bit\n"
                        b"MIME-Version: 1.0\n"
                        b"\n"
                        b"<p>This is a html body! \xf0\x9f\x92\xa9</p>\n"
                        b"\n"
                        b"--===============%(token)d==--\n"
                    )
                    % {b"token": token}
                },
            )
        ]

        em = (
            db_session.query(SESEmailMessage)
            .filter_by(message_id=resp["MessageId"])
            .one()
        )

        assert em.from_ == "noreply@example.com"
        assert em.to == "somebody@example.com"
        assert em.subject == "This is a Subject"

    def test_last_sent(self, db_session):
        to = "me@example.com"
        subject = "I care about this"

        # Send some random emails
        aws_client = pretend.stub(
            send_raw_email=pretend.call_recorder(
                lambda *a, **kw: {"MessageId": str(uuid.uuid4()) + "-ses"}
            )
        )
        sender = SESEmailSender(
            aws_client, sender="DevPyPI <noreply@example.com>", db=db_session
        )
        for address in [to, "somebody_else@example.com"]:
            for subject in [subject, "I do not care about this"]:
                sender.send(
                    f"Foobar <{address}>",
                    EmailMessage(
                        subject=subject, body_text="This is a plain text body"
                    ),
                )

        # Send the last email that we care about
        resp = {"MessageId": str(uuid.uuid4()) + "-ses"}
        aws_client = pretend.stub(
            send_raw_email=pretend.call_recorder(lambda *a, **kw: resp)
        )
        sender = SESEmailSender(
            aws_client, sender="DevPyPI <noreply@example.com>", db=db_session
        )
        sender.send(
            f"Foobar <{to}>",
            EmailMessage(subject=subject, body_text="This is a plain text body"),
        )

        em = (
            db_session.query(SESEmailMessage)
            .filter_by(message_id=resp["MessageId"])
            .one()
        )

        assert sender.last_sent(to, subject) == em.created

    def test_last_sent_none(self, db_session):
        to = "me@example.com"
        subject = "I care about this"
        sender = SESEmailSender(pretend.stub(), sender=pretend.stub(), db=db_session)

        assert sender.last_sent(to, subject) is None
