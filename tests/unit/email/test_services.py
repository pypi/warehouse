# SPDX-License-Identifier: Apache-2.0

import random
import sys
import uuid

import boto3
import pytest

from botocore.stub import Stubber
from jinja2.exceptions import TemplateNotFound
from pyramid_mailer.interfaces import IMailer
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

    def test_creates_service(self, sender_class, pyramid_request):
        mailer = DummyMailer()
        pyramid_request.registry.registerUtility(mailer, IMailer)
        pyramid_request.registry.settings.update(
            {"site.name": "DevPyPI", "mail.sender": "noreply@example.com"}
        )

        service = sender_class.create_service(None, pyramid_request)

        assert isinstance(service, sender_class)
        assert service.mailer is mailer
        assert service.sender == "DevPyPI <noreply@example.com>"

    def test_send(self, sender_class):
        mailer = DummyMailer()
        service = sender_class(mailer, sender="DevPyPI <noreply@example.com>")

        service.send(
            "somebody@example.com",
            EmailMessage(
                subject="a subject", body_text="a body", body_html="a html body"
            ),
        )

        assert len(mailer.outbox) == 1

        msg = mailer.outbox[0]

        assert msg.subject == "a subject"
        assert msg.body == "a body"
        assert msg.html == "a html body"
        assert msg.recipients == ["somebody@example.com"]
        assert msg.sender == "DevPyPI <noreply@example.com>"

    def test_last_sent(self, sender_class):
        mailer = DummyMailer()
        service = sender_class(mailer, sender="DevPyPI <noreply@example.com>")

        assert service.last_sent(to="me@example.com", subject="a subject") is None


class TestConsoleAndSMTPEmailSender:
    def test_send(self, capsys):
        mailer = DummyMailer()
        service = ConsoleAndSMTPEmailSender(
            mailer, sender="DevPyPI <noreply@example.com>"
        )

        service.send(
            "somebody@example.com",
            EmailMessage(
                subject="a subject",
                body_text="a body",
                body_html="a html body",
            ),
        )
        captured = capsys.readouterr()
        expected = """
Email sent
Subject: a subject
From: DevPyPI <noreply@example.com>
To: somebody@example.com
HTML: Visualize at http://localhost:1080
Text: a body"""
        assert captured.out.strip() == expected.strip()


class TestSESEmailSender:
    @pytest.fixture
    def ses_stubber(self):
        client = boto3.session.Session().client(
            "ses",
            region_name="us-west-2",
            aws_access_key_id="foo",
            aws_secret_access_key="bar",
        )
        with Stubber(client) as stubber:
            yield stubber
        stubber.assert_no_pending_responses()

    def test_verify_service(self):
        assert verifyClass(IEmailSender, SESEmailSender)

    def test_creates_service(self, db_request, pyramid_services, mocker):
        aws_session = mocker.create_autospec(boto3.session.Session, instance=True)
        pyramid_services.register_service(aws_session, name="aws.session")
        db_request.registry.settings.update(
            {
                "site.name": "DevPyPI",
                "mail.region": "us-west-2",
                "mail.sender": "noreply@example.com",
            }
        )

        sender = SESEmailSender.create_service(None, db_request)

        aws_session.client.assert_called_once_with("ses", region_name="us-west-2")
        assert sender._client is aws_session.client.return_value
        assert sender._sender == "DevPyPI <noreply@example.com>"
        assert sender._db is db_request.db

    def test_send_with_plaintext(self, db_session, ses_stubber):
        resp = {"MessageId": str(uuid.uuid4()) + "-ses"}
        ses_stubber.add_response(
            "send_raw_email",
            resp,
            {
                "Source": "DevPyPI <noreply@example.com>",
                "Destinations": ["Foobar <somebody@example.com>"],
                "RawMessage": {
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
            },
        )
        sender = SESEmailSender(
            ses_stubber.client, sender="DevPyPI <noreply@example.com>", db=db_session
        )

        sender.send(
            "Foobar <somebody@example.com>",
            EmailMessage(
                subject="This is a Subject", body_text="This is a plain text body"
            ),
        )

        em = (
            db_session.query(SESEmailMessage)
            .filter_by(message_id=resp["MessageId"])
            .one()
        )

        assert em.from_ == "noreply@example.com"
        assert em.to == "somebody@example.com"
        assert em.subject == "This is a Subject"

    def test_send_with_unicode_and_html(self, db_session, ses_stubber):
        # Determine what the random boundary token will be
        random.seed(42)
        token = random.randrange(sys.maxsize)
        random.seed(42)

        resp = {"MessageId": str(uuid.uuid4()) + "-ses"}
        ses_stubber.add_response(
            "send_raw_email",
            resp,
            {
                "Source": "DevPyPI <noreply@example.com>",
                "Destinations": ["Fööbar <somebody@example.com>"],
                "RawMessage": {
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
            },
        )
        sender = SESEmailSender(
            ses_stubber.client, sender="DevPyPI <noreply@example.com>", db=db_session
        )

        sender.send(
            "Fööbar <somebody@example.com>",
            EmailMessage(
                subject="This is a Subject",
                body_text="This is a plain text body",
                body_html="<p>This is a html body! 💩</p>",
            ),
        )

        em = (
            db_session.query(SESEmailMessage)
            .filter_by(message_id=resp["MessageId"])
            .one()
        )

        assert em.from_ == "noreply@example.com"
        assert em.to == "somebody@example.com"
        assert em.subject == "This is a Subject"

    def test_last_sent(self, db_session, ses_stubber):
        to = "me@example.com"
        subject = "I care about this"
        sender = SESEmailSender(
            ses_stubber.client, sender="DevPyPI <noreply@example.com>", db=db_session
        )

        # Send some random emails
        for address in [to, "somebody_else@example.com"]:
            for s in [subject, "I do not care about this"]:
                ses_stubber.add_response(
                    "send_raw_email", {"MessageId": str(uuid.uuid4()) + "-ses"}
                )
                sender.send(
                    f"Foobar <{address}>",
                    EmailMessage(subject=s, body_text="This is a plain text body"),
                )

        # Send the last email that we care about
        resp = {"MessageId": str(uuid.uuid4()) + "-ses"}
        ses_stubber.add_response("send_raw_email", resp)
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

    def test_last_sent_none(self, db_session, mocker):
        to = "me@example.com"
        subject = "I care about this"
        sender = SESEmailSender(mocker.sentinel.client, db=db_session)

        assert sender.last_sent(to, subject) is None
