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

import datetime

import celery.exceptions
import pretend
import pytest

from pyramid_mailer.exceptions import BadHeaders, EncodingError, InvalidMessage
from sqlalchemy.exc import NoResultFound

from warehouse import email
from warehouse.accounts.interfaces import IUserService
from warehouse.email.interfaces import IEmailSender
from warehouse.email.services import EmailMessage

from ...common.db.accounts import EmailFactory, UserFactory
from ...common.db.organizations import TeamFactory


@pytest.mark.parametrize(
    ("user", "address", "expected"),
    [
        (
            pretend.stub(name="", username="", email="me@example.com"),
            None,
            "me@example.com",
        ),
        (
            pretend.stub(name="", username="", email="me@example.com"),
            "other@example.com",
            "other@example.com",
        ),
        (
            pretend.stub(name="", username="foo", email="me@example.com"),
            None,
            "foo <me@example.com>",
        ),
        (
            pretend.stub(name="bar", username="foo", email="me@example.com"),
            None,
            "bar <me@example.com>",
        ),
        (
            pretend.stub(name="bar", username="foo", email="me@example.com"),
            "other@example.com",
            "bar <other@example.com>",
        ),
    ],
)
def test_compute_recipient(user, address, expected):
    email_ = address if address is not None else user.email
    assert email._compute_recipient(user, email_) == expected


@pytest.mark.parametrize(
    ("unauthenticated_userid", "user", "remote_addr", "expected"),
    [
        ("the_users_id", None, "1.2.3.4", False),
        ("some_other_id", None, "1.2.3.4", True),
        (None, pretend.stub(id="the_users_id"), "1.2.3.4", False),
        (None, pretend.stub(id="some_other_id"), "1.2.3.4", True),
        (None, None, "1.2.3.4", False),
        (None, None, "127.0.0.1", True),
    ],
)
def test_redact_ip(unauthenticated_userid, user, remote_addr, expected):
    user_email = pretend.stub(user_id="the_users_id")

    request = pretend.stub(
        _unauthenticated_userid=unauthenticated_userid,
        user=user,
        db=pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda a: pretend.stub(one=lambda: user_email)
            )
        ),
        remote_addr=remote_addr,
    )
    assert email._redact_ip(request, user_email) == expected


def test_redact_ip_email_not_found():
    request = pretend.stub(
        db=pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda a: pretend.stub(one=pretend.raiser(NoResultFound))
            )
        )
    )
    assert email._redact_ip(request, "doesn't matter") is False


class TestSendEmailToUser:
    @pytest.mark.parametrize(
        ("name", "username", "primary_email", "address", "expected"),
        [
            ("", "theuser", "email@example.com", None, "theuser <email@example.com>"),
            (
                "Sally User",
                "theuser",
                "email@example.com",
                None,
                "Sally User <email@example.com>",
            ),
            (
                "",
                "theuser",
                "email@example.com",
                "anotheremail@example.com",
                "theuser <anotheremail@example.com>",
            ),
        ],
    )
    def test_sends_to_user_with_verified(
        self, name, username, primary_email, address, expected, pyramid_request
    ):
        user = pretend.stub(
            name=name,
            username=username,
            primary_email=pretend.stub(email=primary_email, verified=True),
            id="id",
        )

        task = pretend.stub(delay=pretend.call_recorder(lambda *a, **kw: None))
        pyramid_request.task = pretend.call_recorder(lambda x: task)
        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=user.id)
                )
            ),
        )
        pyramid_request.user = user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}
        pyramid_request.remote_addr = "10.69.10.69"

        if address is not None:
            address = pretend.stub(email=address, verified=True)

        msg = EmailMessage(subject="My Subject", body_text="My Body")

        email._send_email_to_user(pyramid_request, user, msg, email=address)

        assert pyramid_request.task.calls == [pretend.call(email.send_email)]
        assert task.delay.calls == [
            pretend.call(
                expected,
                {"subject": "My Subject", "body_text": "My Body", "body_html": None},
                {
                    "tag": "account:email:sent",
                    "user_id": user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": address.email if address else primary_email,
                        "subject": "My Subject",
                        "redact_ip": False,
                    },
                },
            )
        ]

    @pytest.mark.parametrize(
        ("primary_email", "address"),
        [
            ("email@example.com", None),
            ("email@example.com", "anotheremail@example.com"),
        ],
    )
    def test_doesnt_send_with_unverified(self, primary_email, address):
        task = pretend.stub(delay=pretend.call_recorder(lambda *a, **kw: None))
        request = pretend.stub(task=pretend.call_recorder(lambda x: task))

        user = pretend.stub(
            primary_email=pretend.stub(
                email=primary_email, verified=True if address is not None else False
            ),
        )

        if address is not None:
            address = pretend.stub(email=address, verified=False)

        msg = EmailMessage(subject="My Subject", body_text="My Body")

        email._send_email_to_user(request, user, msg, email=address)

        assert request.task.calls == []
        assert task.delay.calls == []

    def test_doesnt_send_within_reset_window(self, pyramid_request, pyramid_services):
        email_service = pretend.stub(
            last_sent=pretend.call_recorder(
                lambda to, subject: datetime.datetime.now()
                - datetime.timedelta(seconds=69)
            )
        )
        pyramid_services.register_service(email_service, IEmailSender, None, name="")

        task = pretend.stub(delay=pretend.call_recorder(lambda *a, **kw: None))
        pyramid_request.task = pretend.call_recorder(lambda x: task)

        address = "foo@example.com"
        user = pretend.stub(primary_email=pretend.stub(email=address, verified=True))

        msg = EmailMessage(subject="My Subject", body_text="My Body")

        email._send_email_to_user(
            pyramid_request, user, msg, repeat_window=datetime.timedelta(seconds=420)
        )

        assert pyramid_request.task.calls == []
        assert task.delay.calls == []

    @pytest.mark.parametrize(
        ("username", "primary_email", "address", "expected"),
        [
            ("theuser", "email@example.com", None, "theuser <email@example.com>"),
            (
                "theuser",
                "email@example.com",
                "anotheremail@example.com",
                "theuser <anotheremail@example.com>",
            ),
        ],
    )
    def test_sends_unverified_with_override(
        self, username, primary_email, address, expected, pyramid_request
    ):
        user = pretend.stub(
            username=username,
            name="",
            primary_email=pretend.stub(
                email=primary_email, verified=True if address is not None else False
            ),
            id="id",
        )

        task = pretend.stub(delay=pretend.call_recorder(lambda *a, **kw: None))
        pyramid_request.task = pretend.call_recorder(lambda x: task)
        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=user.id)
                )
            ),
        )
        pyramid_request.user = user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        if address is not None:
            address = pretend.stub(email=address, verified=False)

        msg = EmailMessage(subject="My Subject", body_text="My Body")

        email._send_email_to_user(
            pyramid_request, user, msg, email=address, allow_unverified=True
        )

        assert pyramid_request.task.calls == [pretend.call(email.send_email)]
        assert task.delay.calls == [
            pretend.call(
                expected,
                {"subject": "My Subject", "body_text": "My Body", "body_html": None},
                {
                    "tag": "account:email:sent",
                    "user_id": user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": address.email if address else primary_email,
                        "subject": "My Subject",
                        "redact_ip": False,
                    },
                },
            )
        ]


class TestSendEmail:
    @pytest.mark.parametrize("delete_user", [True, False])
    def test_send_email_success(self, delete_user, db_session, monkeypatch):
        class FakeMailSender:
            def __init__(self):
                self.emails = []

            def send(self, recipient, msg):
                self.emails.append(
                    {
                        "subject": msg.subject,
                        "body": msg.body_text,
                        "html": msg.body_html,
                        "recipient": recipient,
                    }
                )

        class FakeUser:
            def __init__(self):
                self.events = []

            def record_event(self, tag, request=None, additional=None):
                self.events.append(
                    {
                        "request": request,
                        "tag": tag,
                        "additional": additional,
                    }
                )

        class FakeUserEventService:
            def __init__(self):
                self.user = FakeUser()

            def get_user(self, user_id):
                if delete_user:
                    return None
                return self.user

        user_service = FakeUserEventService()
        sender = FakeMailSender()
        task = pretend.stub()
        request = pretend.stub(
            find_service=pretend.call_recorder(
                lambda svc, context=None, name=None: {
                    IUserService: user_service,
                    IEmailSender: sender,
                }.get(svc)
            ),
            remote_addr="0.0.0.0",
        )
        user_id = pretend.stub()

        msg = EmailMessage(subject="subject", body_text="body")

        email.send_email(
            task,
            request,
            "recipient",
            {
                "subject": msg.subject,
                "body_text": msg.body_text,
                "body_html": msg.body_html,
            },
            {
                "tag": "account:email:sent",
                "user_id": user_id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": "recipient",
                    "subject": msg.subject,
                    "redact_ip": False,
                },
            },
        )

        assert request.find_service.calls == [
            pretend.call(IEmailSender),
            pretend.call(IUserService, context=None),
        ]
        assert sender.emails == [
            {
                "subject": "subject",
                "body": "body",
                "html": None,
                "recipient": "recipient",
            }
        ]
        if delete_user:
            assert user_service.user.events == []
        else:
            assert user_service.user.events == [
                {
                    "tag": "account:email:sent",
                    "request": request,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "recipient",
                        "subject": msg.subject,
                        "redact_ip": False,
                    },
                }
            ]

    def test_send_email_failure_retry(self, monkeypatch):
        exc = Exception()

        sentry_sdk = pretend.stub(
            capture_exception=pretend.call_recorder(lambda s: None)
        )
        monkeypatch.setattr(email, "sentry_sdk", sentry_sdk)

        class FakeMailSender:
            def send(self, recipient, msg):
                raise exc

        class Task:
            @staticmethod
            @pretend.call_recorder
            def retry(exc):
                raise celery.exceptions.Retry

        sender, task = FakeMailSender(), Task()
        request = pretend.stub(find_service=lambda *a, **kw: sender)
        user_id = pretend.stub()
        msg = EmailMessage(subject="subject", body_text="body")

        with pytest.raises(celery.exceptions.Retry):
            email.send_email(
                task,
                request,
                "recipient",
                {
                    "subject": msg.subject,
                    "body_text": msg.body_text,
                    "body_html": msg.body_html,
                },
                {
                    "tag": "account:email:sent",
                    "user_id": user_id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "recipient",
                        "subject": msg.subject,
                        "redact_ip": False,
                    },
                },
            )

        assert sentry_sdk.capture_exception.calls == [pretend.call(exc)]
        assert task.retry.calls == [pretend.call(exc=exc)]

    @pytest.mark.parametrize("exc", [InvalidMessage, BadHeaders, EncodingError])
    def test_send_email_failure_doesnt_retry(self, monkeypatch, exc):
        class FakeMailSender:
            def send(self, recipient, msg):
                raise exc

        class Task:
            @staticmethod
            @pretend.call_recorder
            def retry(exc):
                raise celery.exceptions.Retry

        sender, task = FakeMailSender(), Task()
        request = pretend.stub(find_service=lambda *a, **kw: sender)
        user_id = pretend.stub()
        msg = EmailMessage(subject="subject", body_text="body")

        with pytest.raises(exc):
            email.send_email(
                task,
                request,
                "recipient",
                {
                    "subject": msg.subject,
                    "body_text": msg.body_text,
                    "body_html": msg.body_html,
                },
                {
                    "tag": "account:email:sent",
                    "user_id": user_id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "recipient",
                        "subject": msg.subject,
                        "redact_ip": False,
                    },
                },
            )

        assert task.retry.calls == []


class TestSendAdminNewOrganizationRequestedEmail:
    def test_send_admin_new_organization_requested_email(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        admin_user = pretend.stub(
            id="admin",
            username="admin",
            name="PyPI Adminstrator",
            email="admin@pypi.org",
            primary_email=pretend.stub(email="admin@pypi.org", verified=True),
        )
        initiator_user = pretend.stub(
            id="id",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        organization_id = "id"
        organization_name = "example"

        subject_renderer = pyramid_config.testing_add_renderer(
            "email/admin-new-organization-requested/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/admin-new-organization-requested/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/admin-new-organization-requested/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=admin_user.id)
                )
            ),
        )
        pyramid_request.user = initiator_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        result = email.send_admin_new_organization_requested_email(
            pyramid_request,
            admin_user,
            organization_name=organization_name,
            initiator_username=initiator_user.username,
            organization_id=organization_id,
        )

        assert result == {
            "organization_name": organization_name,
            "initiator_username": initiator_user.username,
            "organization_id": organization_id,
        }
        subject_renderer.assert_(
            organization_name=organization_name,
            initiator_username=initiator_user.username,
            organization_id=organization_id,
        )
        body_renderer.assert_(
            organization_name=organization_name,
            initiator_username=initiator_user.username,
            organization_id=organization_id,
        )
        html_renderer.assert_(
            organization_name=organization_name,
            initiator_username=initiator_user.username,
            organization_id=organization_id,
        )
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{admin_user.name} <{admin_user.email}>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": admin_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": admin_user.email,
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            )
        ]


class TestSendAdminNewOrganizationApprovedEmail:
    def test_send_admin_new_organization_approved_email(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        admin_user = pretend.stub(
            id="admin",
            username="admin",
            name="PyPI Adminstrator",
            email="admin@pypi.org",
            primary_email=pretend.stub(email="admin@pypi.org", verified=True),
        )
        initiator_user = pretend.stub(
            id="id",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        organization_name = "example"
        message = "example message"

        subject_renderer = pyramid_config.testing_add_renderer(
            "email/admin-new-organization-approved/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/admin-new-organization-approved/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/admin-new-organization-approved/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=admin_user.id)
                )
            ),
        )
        pyramid_request.user = initiator_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        result = email.send_admin_new_organization_approved_email(
            pyramid_request,
            admin_user,
            organization_name=organization_name,
            initiator_username=initiator_user.username,
            message=message,
        )

        assert result == {
            "organization_name": organization_name,
            "initiator_username": initiator_user.username,
            "message": message,
        }
        subject_renderer.assert_(
            organization_name=organization_name,
            initiator_username=initiator_user.username,
            message=message,
        )
        body_renderer.assert_(
            organization_name=organization_name,
            initiator_username=initiator_user.username,
            message=message,
        )
        html_renderer.assert_(
            organization_name=organization_name,
            initiator_username=initiator_user.username,
            message=message,
        )
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{admin_user.name} <{admin_user.email}>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": admin_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": admin_user.email,
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            )
        ]


class TestSendAdminNewOrganizationDeclinedEmail:
    def test_send_admin_new_organization_declined_email(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        admin_user = pretend.stub(
            id="admin",
            username="admin",
            name="PyPI Adminstrator",
            email="admin@pypi.org",
            primary_email=pretend.stub(email="admin@pypi.org", verified=True),
        )
        initiator_user = pretend.stub(
            id="id",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        organization_name = "example"
        message = "example message"

        subject_renderer = pyramid_config.testing_add_renderer(
            "email/admin-new-organization-declined/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/admin-new-organization-declined/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/admin-new-organization-declined/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=admin_user.id)
                )
            ),
        )
        pyramid_request.user = initiator_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        result = email.send_admin_new_organization_declined_email(
            pyramid_request,
            admin_user,
            organization_name=organization_name,
            initiator_username=initiator_user.username,
            message=message,
        )

        assert result == {
            "organization_name": organization_name,
            "initiator_username": initiator_user.username,
            "message": message,
        }
        subject_renderer.assert_(
            organization_name=organization_name,
            initiator_username=initiator_user.username,
            message=message,
        )
        body_renderer.assert_(
            organization_name=organization_name,
            initiator_username=initiator_user.username,
            message=message,
        )
        html_renderer.assert_(
            organization_name=organization_name,
            initiator_username=initiator_user.username,
            message=message,
        )
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{admin_user.name} <{admin_user.email}>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": admin_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": admin_user.email,
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            )
        ]


class TestSendPasswordResetEmail:
    @pytest.mark.parametrize(
        ("verified", "email_addr"),
        [
            (True, None),
            (False, None),
            (True, "other@example.com"),
            (False, "other@example.com"),
        ],
    )
    def test_send_password_reset_email(
        self,
        verified,
        email_addr,
        pyramid_request,
        pyramid_config,
        token_service,
        metrics,
        monkeypatch,
    ):
        stub_user = pretend.stub(
            id="id",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=verified),
            username="username_value",
            name="name_value",
            last_login="last_login",
            password_date="password_date",
        )
        if email_addr is None:
            stub_email = None
        else:
            stub_email = pretend.stub(email=email_addr, verified=verified)
        pyramid_request.method = "POST"
        token_service.dumps = pretend.call_recorder(lambda a: "TOKEN")

        subject_renderer = pyramid_config.testing_add_renderer(
            "email/password-reset/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/password-reset/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/password-reset/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=stub_user.id)
                )
            ),
        )
        pyramid_request.user = stub_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        result = email.send_password_reset_email(
            pyramid_request, (stub_user, stub_email)
        )

        assert result == {
            "token": "TOKEN",
            "username": stub_user.username,
            "n_hours": token_service.max_age // 60 // 60,
        }
        subject_renderer.assert_()
        body_renderer.assert_(token="TOKEN", username=stub_user.username)
        html_renderer.assert_(token="TOKEN", username=stub_user.username)
        assert token_service.dumps.calls == [
            pretend.call(
                {
                    "action": "password-reset",
                    "user.id": str(stub_user.id),
                    "user.last_login": str(stub_user.last_login),
                    "user.password_date": str(stub_user.password_date),
                }
            )
        ]
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                "name_value <"
                + (stub_user.email if email_addr is None else email_addr)
                + ">",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": (
                            "other@example.com" if stub_email else "email@example.com"
                        ),
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            )
        ]
        assert metrics.increment.calls == [
            pretend.call(
                "warehouse.emails.scheduled",
                tags=[
                    "template_name:password-reset",
                    "allow_unverified:True",
                    "repeat_window:none",
                ],
            )
        ]


class TestEmailVerificationEmail:
    def test_email_verification_email(
        self, pyramid_request, pyramid_config, token_service, monkeypatch
    ):
        stub_user = pretend.stub(
            id="id", username=None, name=None, email="foo@example.com"
        )
        stub_email = pretend.stub(id="id", email="email@example.com", verified=False)
        pyramid_request.method = "POST"
        token_service.dumps = pretend.call_recorder(lambda a: "TOKEN")

        subject_renderer = pyramid_config.testing_add_renderer(
            "email/verify-email/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/verify-email/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/verify-email/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=stub_user.id)
                )
            ),
        )
        pyramid_request.user = stub_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        result = email.send_email_verification_email(
            pyramid_request, (stub_user, stub_email)
        )

        assert result == {
            "token": "TOKEN",
            "email_address": stub_email.email,
            "n_hours": token_service.max_age // 60 // 60,
        }
        subject_renderer.assert_()
        body_renderer.assert_(token="TOKEN", email_address=stub_email.email)
        html_renderer.assert_(token="TOKEN", email_address=stub_email.email)
        assert token_service.dumps.calls == [
            pretend.call({"action": "email-verify", "email.id": str(stub_email.id)})
        ]
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                stub_email.email,
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": stub_email.email,
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            )
        ]


class TestNewEmailAddedEmails:
    def test_new_email_added_emails(self, pyramid_request, pyramid_config, monkeypatch):
        stub_user = pretend.stub(
            id="id", username="username", name=None, email="foo@example.com"
        )
        stub_email = pretend.stub(id="id", email="email@example.com", verified=False)
        new_email_address = "new@example.com"
        pyramid_request.method = "POST"

        subject_renderer = pyramid_config.testing_add_renderer(
            "email/new-email-added/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/new-email-added/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/new-email-added/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=stub_user.id)
                )
            ),
        )
        pyramid_request.user = stub_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        result = email.send_new_email_added_email(
            pyramid_request,
            (stub_user, stub_email),
            new_email_address=new_email_address,
        )

        assert result == {
            "username": stub_user.username,
            "new_email_address": new_email_address,
        }
        subject_renderer.assert_()
        body_renderer.assert_(new_email_address=new_email_address)
        html_renderer.assert_(new_email_address=new_email_address)
        assert pyramid_request.task.calls == []
        assert send_email.delay.calls == []


class TestPasswordChangeEmail:
    def test_password_change_email(self, pyramid_request, pyramid_config, monkeypatch):
        stub_user = pretend.stub(
            id="id",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        subject_renderer = pyramid_config.testing_add_renderer(
            "email/password-change/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/password-change/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/password-change/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=stub_user.id)
                )
            ),
        )
        pyramid_request.user = stub_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        result = email.send_password_change_email(pyramid_request, stub_user)

        assert result == {"username": stub_user.username}
        subject_renderer.assert_()
        body_renderer.assert_(username=stub_user.username)
        html_renderer.assert_(username=stub_user.username)
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{stub_user.username} <{stub_user.email}>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": stub_user.email,
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            )
        ]

    def test_password_change_email_unverified(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        stub_user = pretend.stub(
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=False),
        )
        subject_renderer = pyramid_config.testing_add_renderer(
            "email/password-change/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/password-change/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/password-change/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=stub_user.id)
                )
            ),
        )
        pyramid_request.user = stub_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        result = email.send_password_change_email(pyramid_request, stub_user)

        assert result == {"username": stub_user.username}
        subject_renderer.assert_()
        body_renderer.assert_(username=stub_user.username)
        html_renderer.assert_(username=stub_user.username)
        assert pyramid_request.task.calls == []
        assert send_email.delay.calls == []


class TestPasswordCompromisedHIBPEmail:
    @pytest.mark.parametrize("verified", [True, False])
    def test_password_compromised_email_hibp(
        self, pyramid_request, pyramid_config, monkeypatch, verified
    ):
        stub_user = pretend.stub(
            id="id",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=verified),
        )
        subject_renderer = pyramid_config.testing_add_renderer(
            "email/password-compromised-hibp/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/password-compromised-hibp/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/password-compromised-hibp/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=stub_user.id)
                )
            ),
        )
        pyramid_request.user = stub_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        result = email.send_password_compromised_email_hibp(pyramid_request, stub_user)

        assert result == {}
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{stub_user.username} <{stub_user.email}>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": stub_user.email,
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            )
        ]


class TestTokenLeakEmail:
    @pytest.mark.parametrize("verified", [True, False])
    def test_token_leak_email(
        self, pyramid_request, pyramid_config, monkeypatch, verified
    ):
        stub_user = pretend.stub(
            id=3,
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=verified),
        )
        pyramid_request.user = None
        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(one=lambda: stub_user)
            ),
        )

        subject_renderer = pyramid_config.testing_add_renderer(
            "email/token-compromised-leak/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/token-compromised-leak/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/token-compromised-leak/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        result = email.send_token_compromised_email_leak(
            pyramid_request, stub_user, public_url="http://example.com", origin="github"
        )

        assert result == {
            "username": "username",
            "public_url": "http://example.com",
            "origin": "github",
        }
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{stub_user.username} <{stub_user.email}>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": 3,
                    "additional": {
                        "from_": None,
                        "to": "email@example.com",
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            )
        ]


class TestPasswordCompromisedEmail:
    @pytest.mark.parametrize("verified", [True, False])
    def test_password_compromised_email(
        self, pyramid_request, pyramid_config, monkeypatch, verified
    ):
        stub_user = pretend.stub(
            id="id",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=verified),
        )
        subject_renderer = pyramid_config.testing_add_renderer(
            "email/password-compromised/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/password-compromised/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/password-compromised/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=stub_user.id)
                )
            ),
        )
        pyramid_request.user = stub_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        result = email.send_password_compromised_email(pyramid_request, stub_user)

        assert result == {}
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{stub_user.username} <{stub_user.email}>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": stub_user.email,
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            )
        ]


class Test2FAonUploadEmail:
    def test_send_two_factor_not_yet_enabled_email(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        stub_user = pretend.stub(
            id="id",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
            has_2fa=False,
        )
        subject_renderer = pyramid_config.testing_add_renderer(
            "email/two-factor-not-yet-enabled/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/two-factor-not-yet-enabled/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/two-factor-not-yet-enabled/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=stub_user.id)
                )
            ),
        )
        pyramid_request.user = stub_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        result = email.send_two_factor_not_yet_enabled_email(
            pyramid_request,
            stub_user,
        )

        assert result == {"username": stub_user.username}
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{stub_user.username} <{stub_user.email}>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": stub_user.email,
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            )
        ]


class TestAccountDeletionEmail:
    def test_account_deletion_email(
        self, pyramid_request, pyramid_config, metrics, monkeypatch
    ):
        stub_user = pretend.stub(
            id="id",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        subject_renderer = pyramid_config.testing_add_renderer(
            "email/account-deleted/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/account-deleted/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/account-deleted/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=stub_user.id)
                )
            ),
        )
        pyramid_request.user = stub_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        result = email.send_account_deletion_email(pyramid_request, stub_user)

        assert result == {"username": stub_user.username}
        subject_renderer.assert_()
        body_renderer.assert_(username=stub_user.username)
        html_renderer.assert_(username=stub_user.username)
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{stub_user.username} <{stub_user.email}>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": stub_user.email,
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            )
        ]

        assert metrics.increment.calls == [
            pretend.call(
                "warehouse.emails.scheduled",
                tags=[
                    "template_name:account-deleted",
                    "allow_unverified:False",
                    "repeat_window:none",
                ],
            )
        ]

    def test_account_deletion_email_unverified(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        stub_user = pretend.stub(
            id="id",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=False),
        )
        subject_renderer = pyramid_config.testing_add_renderer(
            "email/account-deleted/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/account-deleted/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/account-deleted/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=stub_user.id)
                )
            ),
        )
        pyramid_request.user = stub_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        result = email.send_account_deletion_email(pyramid_request, stub_user)

        assert result == {"username": stub_user.username}
        subject_renderer.assert_()
        body_renderer.assert_(username=stub_user.username)
        html_renderer.assert_(username=stub_user.username)
        assert pyramid_request.task.calls == []
        assert send_email.delay.calls == []


class TestPrimaryEmailChangeEmail:
    def test_primary_email_change_email(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        stub_user = pretend.stub(
            id="id", email="new_email@example.com", username="username", name=""
        )
        subject_renderer = pyramid_config.testing_add_renderer(
            "email/primary-email-change/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/primary-email-change/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/primary-email-change/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=stub_user.id)
                )
            ),
        )
        pyramid_request.user = stub_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        result = email.send_primary_email_change_email(
            pyramid_request,
            (stub_user, pretend.stub(email="old_email@example.com", verified=True)),
        )

        assert result == {
            "username": stub_user.username,
            "old_email": "old_email@example.com",
            "new_email": stub_user.email,
        }
        subject_renderer.assert_()
        body_renderer.assert_(username=stub_user.username)
        html_renderer.assert_(username=stub_user.username)
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                "username <old_email@example.com>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "old_email@example.com",
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            )
        ]

    def test_primary_email_change_email_unverified(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        stub_user = pretend.stub(
            id="id", email="new_email@example.com", username="username", name=""
        )
        subject_renderer = pyramid_config.testing_add_renderer(
            "email/primary-email-change/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/primary-email-change/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/primary-email-change/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=stub_user.id)
                )
            ),
        )
        pyramid_request.user = stub_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        result = email.send_primary_email_change_email(
            pyramid_request,
            (stub_user, pretend.stub(email="old_email@example.com", verified=False)),
        )

        assert result == {
            "username": stub_user.username,
            "old_email": "old_email@example.com",
            "new_email": stub_user.email,
        }
        subject_renderer.assert_()
        body_renderer.assert_(username=stub_user.username)
        html_renderer.assert_(username=stub_user.username)
        assert pyramid_request.task.calls == []
        assert send_email.delay.calls == []


class TestSendNewOrganizationRequestedEmail:
    def test_send_new_organization_requested_email(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        initiator_user = pretend.stub(
            id="id",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        organization_name = "example"

        subject_renderer = pyramid_config.testing_add_renderer(
            "email/new-organization-requested/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/new-organization-requested/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/new-organization-requested/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=initiator_user.id)
                )
            ),
        )
        pyramid_request.user = initiator_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        result = email.send_new_organization_requested_email(
            pyramid_request,
            initiator_user,
            organization_name=organization_name,
        )

        assert result == {"organization_name": organization_name}
        subject_renderer.assert_(organization_name=organization_name)
        body_renderer.assert_(organization_name=organization_name)
        html_renderer.assert_(organization_name=organization_name)
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{initiator_user.username} <{initiator_user.email}>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": initiator_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": initiator_user.email,
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            )
        ]


class TestSendNewOrganizationApprovedEmail:
    def test_send_new_organization_approved_email(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        initiator_user = pretend.stub(
            id="id",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        organization_name = "example"
        message = "example message"

        subject_renderer = pyramid_config.testing_add_renderer(
            "email/new-organization-approved/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/new-organization-approved/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/new-organization-approved/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=initiator_user.id)
                )
            ),
        )
        pyramid_request.user = initiator_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        result = email.send_new_organization_approved_email(
            pyramid_request,
            initiator_user,
            organization_name=organization_name,
            message=message,
        )

        assert result == {
            "organization_name": organization_name,
            "message": message,
        }
        subject_renderer.assert_(
            organization_name=organization_name,
            message=message,
        )
        body_renderer.assert_(
            organization_name=organization_name,
            message=message,
        )
        html_renderer.assert_(
            organization_name=organization_name,
            message=message,
        )
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{initiator_user.username} <{initiator_user.email}>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": initiator_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": initiator_user.email,
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            )
        ]


class TestSendNewOrganizationDeclinedEmail:
    def test_send_new_organization_declined_email(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        initiator_user = pretend.stub(
            id="id",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        organization_name = "example"
        message = "example message"

        subject_renderer = pyramid_config.testing_add_renderer(
            "email/new-organization-declined/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/new-organization-declined/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/new-organization-declined/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=initiator_user.id)
                )
            ),
        )
        pyramid_request.user = initiator_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        result = email.send_new_organization_declined_email(
            pyramid_request,
            initiator_user,
            organization_name=organization_name,
            message=message,
        )

        assert result == {
            "organization_name": organization_name,
            "message": message,
        }
        subject_renderer.assert_(
            organization_name=organization_name,
            message=message,
        )
        body_renderer.assert_(
            organization_name=organization_name,
            message=message,
        )
        html_renderer.assert_(
            organization_name=organization_name,
            message=message,
        )
        assert send_email.delay.calls == [
            pretend.call(
                f"{initiator_user.username} <{initiator_user.email}>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": initiator_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": initiator_user.email,
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            )
        ]


class TestOrganizationProjectEmails:
    @pytest.fixture
    def organization_project(self, pyramid_user):
        self.user = pyramid_user
        self.organization_name = "exampleorganization"
        self.project_name = "exampleproject"

    @pytest.mark.parametrize(
        ("email_template_name", "send_organization_project_email"),
        [
            ("organization-project-added", email.send_organization_project_added_email),
            (
                "organization-project-removed",
                email.send_organization_project_removed_email,
            ),
        ],
    )
    def test_send_organization_project_email(
        self,
        db_request,
        organization_project,
        make_email_renderers,
        send_email,
        email_template_name,
        send_organization_project_email,
    ):
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            email_template_name
        )

        result = send_organization_project_email(
            db_request,
            self.user,
            organization_name=self.organization_name,
            project_name=self.project_name,
        )

        assert result == {
            "organization_name": self.organization_name,
            "project_name": self.project_name,
        }
        subject_renderer.assert_(**result)
        body_renderer.assert_(**result)
        html_renderer.assert_(**result)
        assert db_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{self.user.name} <{self.user.email}>",
                {
                    "subject": subject_renderer.string_response,
                    "body_text": body_renderer.string_response,
                    "body_html": (
                        f"<html>\n"
                        f"<head></head>\n"
                        f"<body><p>{html_renderer.string_response}</p></body>\n"
                        f"</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": self.user.id,
                    "additional": {
                        "from_": db_request.registry.settings["mail.sender"],
                        "to": self.user.email,
                        "subject": subject_renderer.string_response,
                        "redact_ip": False,
                    },
                },
            )
        ]


class TestOrganizationMemberEmails:
    @pytest.fixture
    def organization_invite(self, pyramid_user):
        self.initiator_user = pyramid_user
        self.user = UserFactory.create()
        EmailFactory.create(user=self.user, verified=True)
        self.desired_role = "Manager"
        self.organization_name = "example"
        self.message = "test message"
        self.email_token = "token"
        self.token_age = 72 * 60 * 60

    def test_send_organization_member_invited_email(
        self,
        db_request,
        organization_invite,
        make_email_renderers,
        send_email,
    ):
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "organization-member-invited"
        )

        result = email.send_organization_member_invited_email(
            db_request,
            self.initiator_user,
            user=self.user,
            desired_role=self.desired_role,
            initiator_username=self.initiator_user.username,
            organization_name=self.organization_name,
            email_token=self.email_token,
            token_age=self.token_age,
        )

        assert result == {
            "username": self.user.username,
            "desired_role": self.desired_role,
            "initiator_username": self.initiator_user.username,
            "n_hours": self.token_age // 60 // 60,
            "organization_name": self.organization_name,
            "token": self.email_token,
        }
        subject_renderer.assert_(**result)
        body_renderer.assert_(**result)
        html_renderer.assert_(**result)
        assert db_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{self.initiator_user.name} <{self.initiator_user.email}>",
                {
                    "subject": subject_renderer.string_response,
                    "body_text": body_renderer.string_response,
                    "body_html": (
                        f"<html>\n"
                        f"<head></head>\n"
                        f"<body><p>{html_renderer.string_response}</p></body>\n"
                        f"</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": self.initiator_user.id,
                    "additional": {
                        "from_": db_request.registry.settings["mail.sender"],
                        "to": self.initiator_user.email,
                        "subject": subject_renderer.string_response,
                        "redact_ip": False,
                    },
                },
            )
        ]

    def test_send_organization_role_verification_email(
        self,
        db_request,
        organization_invite,
        make_email_renderers,
        send_email,
    ):
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "verify-organization-role"
        )

        result = email.send_organization_role_verification_email(
            db_request,
            self.user,
            desired_role=self.desired_role,
            initiator_username=self.initiator_user.username,
            organization_name=self.organization_name,
            email_token=self.email_token,
            token_age=self.token_age,
        )

        assert result == {
            "username": self.user.username,
            "desired_role": self.desired_role,
            "initiator_username": self.initiator_user.username,
            "n_hours": self.token_age // 60 // 60,
            "organization_name": self.organization_name,
            "token": self.email_token,
        }
        subject_renderer.assert_(**result)
        body_renderer.assert_(**result)
        html_renderer.assert_(**result)
        assert db_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{self.user.name} <{self.user.email}>",
                {
                    "subject": subject_renderer.string_response,
                    "body_text": body_renderer.string_response,
                    "body_html": (
                        f"<html>\n"
                        f"<head></head>\n"
                        f"<body><p>{html_renderer.string_response}</p></body>\n"
                        f"</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": self.user.id,
                    "additional": {
                        "from_": db_request.registry.settings["mail.sender"],
                        "to": self.user.email,
                        "subject": subject_renderer.string_response,
                        "redact_ip": True,
                    },
                },
            )
        ]

    def test_send_organization_member_invite_canceled_email(
        self,
        db_request,
        organization_invite,
        make_email_renderers,
        send_email,
    ):
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "organization-member-invite-canceled"
        )

        result = email.send_organization_member_invite_canceled_email(
            db_request,
            self.initiator_user,
            user=self.user,
            organization_name=self.organization_name,
        )

        assert result == {
            "username": self.user.username,
            "organization_name": self.organization_name,
        }
        subject_renderer.assert_(**result)
        body_renderer.assert_(**result)
        html_renderer.assert_(**result)
        assert db_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{self.initiator_user.name} <{self.initiator_user.email}>",
                {
                    "subject": subject_renderer.string_response,
                    "body_text": body_renderer.string_response,
                    "body_html": (
                        f"<html>\n"
                        f"<head></head>\n"
                        f"<body><p>{html_renderer.string_response}</p></body>\n"
                        f"</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": self.initiator_user.id,
                    "additional": {
                        "from_": db_request.registry.settings["mail.sender"],
                        "to": self.initiator_user.email,
                        "subject": subject_renderer.string_response,
                        "redact_ip": False,
                    },
                },
            )
        ]

    def test_send_canceled_as_invited_organization_member_email(
        self,
        db_request,
        organization_invite,
        make_email_renderers,
        send_email,
    ):
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "canceled-as-invited-organization-member"
        )

        result = email.send_canceled_as_invited_organization_member_email(
            db_request,
            self.user,
            organization_name=self.organization_name,
        )

        assert result == {
            "username": self.user.username,
            "organization_name": self.organization_name,
        }
        subject_renderer.assert_(**result)
        body_renderer.assert_(**result)
        html_renderer.assert_(**result)
        assert db_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{self.user.name} <{self.user.email}>",
                {
                    "subject": subject_renderer.string_response,
                    "body_text": body_renderer.string_response,
                    "body_html": (
                        f"<html>\n"
                        f"<head></head>\n"
                        f"<body><p>{html_renderer.string_response}</p></body>\n"
                        f"</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": self.user.id,
                    "additional": {
                        "from_": db_request.registry.settings["mail.sender"],
                        "to": self.user.email,
                        "subject": subject_renderer.string_response,
                        "redact_ip": True,
                    },
                },
            )
        ]

    def test_send_organization_member_invite_declined_email(
        self,
        db_request,
        organization_invite,
        make_email_renderers,
        send_email,
    ):
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "organization-member-invite-declined"
        )

        result = email.send_organization_member_invite_declined_email(
            db_request,
            self.initiator_user,
            user=self.user,
            organization_name=self.organization_name,
            message=self.message,
        )

        assert result == {
            "username": self.user.username,
            "organization_name": self.organization_name,
            "message": self.message,
        }
        subject_renderer.assert_(**result)
        body_renderer.assert_(**result)
        html_renderer.assert_(**result)
        assert db_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{self.initiator_user.name} <{self.initiator_user.email}>",
                {
                    "subject": subject_renderer.string_response,
                    "body_text": body_renderer.string_response,
                    "body_html": (
                        f"<html>\n"
                        f"<head></head>\n"
                        f"<body><p>{html_renderer.string_response}</p></body>\n"
                        f"</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": self.initiator_user.id,
                    "additional": {
                        "from_": db_request.registry.settings["mail.sender"],
                        "to": self.initiator_user.email,
                        "subject": subject_renderer.string_response,
                        "redact_ip": False,
                    },
                },
            )
        ]

    def test_send_declined_as_invited_organization_member_email(
        self,
        db_request,
        organization_invite,
        make_email_renderers,
        send_email,
    ):
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "declined-as-invited-organization-member"
        )

        result = email.send_declined_as_invited_organization_member_email(
            db_request,
            self.user,
            organization_name=self.organization_name,
        )

        assert result == {
            "username": self.user.username,
            "organization_name": self.organization_name,
        }
        subject_renderer.assert_(**result)
        body_renderer.assert_(**result)
        html_renderer.assert_(**result)
        assert db_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{self.user.name} <{self.user.email}>",
                {
                    "subject": subject_renderer.string_response,
                    "body_text": body_renderer.string_response,
                    "body_html": (
                        f"<html>\n"
                        f"<head></head>\n"
                        f"<body><p>{html_renderer.string_response}</p></body>\n"
                        f"</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": self.user.id,
                    "additional": {
                        "from_": db_request.registry.settings["mail.sender"],
                        "to": self.user.email,
                        "subject": subject_renderer.string_response,
                        "redact_ip": True,
                    },
                },
            )
        ]

    def test_send_organization_member_added_email(
        self,
        db_request,
        organization_invite,
        make_email_renderers,
        send_email,
    ):
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "organization-member-added"
        )

        result = email.send_organization_member_added_email(
            db_request,
            self.initiator_user,
            user=self.user,
            submitter=self.initiator_user,
            organization_name=self.organization_name,
            role=self.desired_role,
        )

        assert result == {
            "username": self.user.username,
            "submitter": self.initiator_user.username,
            "organization_name": self.organization_name,
            "role": self.desired_role,
        }
        subject_renderer.assert_(**result)
        body_renderer.assert_(**result)
        html_renderer.assert_(**result)
        assert db_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{self.initiator_user.name} <{self.initiator_user.email}>",
                {
                    "subject": subject_renderer.string_response,
                    "body_text": body_renderer.string_response,
                    "body_html": (
                        f"<html>\n"
                        f"<head></head>\n"
                        f"<body><p>{html_renderer.string_response}</p></body>\n"
                        f"</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": self.initiator_user.id,
                    "additional": {
                        "from_": db_request.registry.settings["mail.sender"],
                        "to": self.initiator_user.email,
                        "subject": subject_renderer.string_response,
                        "redact_ip": False,
                    },
                },
            )
        ]

    def test_send_added_as_organization_email(
        self,
        db_request,
        organization_invite,
        make_email_renderers,
        send_email,
    ):
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "added-as-organization-member"
        )

        result = email.send_added_as_organization_member_email(
            db_request,
            self.user,
            submitter=self.initiator_user,
            organization_name=self.organization_name,
            role=self.desired_role,
        )

        assert result == {
            "username": self.user.username,
            "submitter": self.initiator_user.username,
            "organization_name": self.organization_name,
            "role": self.desired_role,
        }
        subject_renderer.assert_(**result)
        body_renderer.assert_(**result)
        html_renderer.assert_(**result)
        assert db_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{self.user.name} <{self.user.email}>",
                {
                    "subject": subject_renderer.string_response,
                    "body_text": body_renderer.string_response,
                    "body_html": (
                        f"<html>\n"
                        f"<head></head>\n"
                        f"<body><p>{html_renderer.string_response}</p></body>\n"
                        f"</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": self.user.id,
                    "additional": {
                        "from_": db_request.registry.settings["mail.sender"],
                        "to": self.user.email,
                        "subject": subject_renderer.string_response,
                        "redact_ip": True,
                    },
                },
            )
        ]

    def test_send_organization_member_removed_email(
        self,
        db_request,
        organization_invite,
        make_email_renderers,
        send_email,
    ):
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "organization-member-removed"
        )

        result = email.send_organization_member_removed_email(
            db_request,
            self.initiator_user,
            user=self.user,
            submitter=self.initiator_user,
            organization_name=self.organization_name,
        )

        assert result == {
            "username": self.user.username,
            "submitter": self.initiator_user.username,
            "organization_name": self.organization_name,
        }
        subject_renderer.assert_(**result)
        body_renderer.assert_(**result)
        html_renderer.assert_(**result)
        assert db_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{self.initiator_user.name} <{self.initiator_user.email}>",
                {
                    "subject": subject_renderer.string_response,
                    "body_text": body_renderer.string_response,
                    "body_html": (
                        f"<html>\n"
                        f"<head></head>\n"
                        f"<body><p>{html_renderer.string_response}</p></body>\n"
                        f"</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": self.initiator_user.id,
                    "additional": {
                        "from_": db_request.registry.settings["mail.sender"],
                        "to": self.initiator_user.email,
                        "subject": subject_renderer.string_response,
                        "redact_ip": False,
                    },
                },
            )
        ]

    def test_send_removed_as_organization_email(
        self,
        db_request,
        organization_invite,
        make_email_renderers,
        send_email,
    ):
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "removed-as-organization-member"
        )

        result = email.send_removed_as_organization_member_email(
            db_request,
            self.user,
            submitter=self.initiator_user,
            organization_name=self.organization_name,
        )

        assert result == {
            "username": self.user.username,
            "submitter": self.initiator_user.username,
            "organization_name": self.organization_name,
        }
        subject_renderer.assert_(**result)
        body_renderer.assert_(**result)
        html_renderer.assert_(**result)
        assert db_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{self.user.name} <{self.user.email}>",
                {
                    "subject": subject_renderer.string_response,
                    "body_text": body_renderer.string_response,
                    "body_html": (
                        f"<html>\n"
                        f"<head></head>\n"
                        f"<body><p>{html_renderer.string_response}</p></body>\n"
                        f"</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": self.user.id,
                    "additional": {
                        "from_": db_request.registry.settings["mail.sender"],
                        "to": self.user.email,
                        "subject": subject_renderer.string_response,
                        "redact_ip": True,
                    },
                },
            )
        ]

    def test_send_organization_member_role_changed_email(
        self,
        db_request,
        organization_invite,
        make_email_renderers,
        send_email,
    ):
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "organization-member-role-changed"
        )

        result = email.send_organization_member_role_changed_email(
            db_request,
            self.initiator_user,
            user=self.user,
            submitter=self.initiator_user,
            organization_name=self.organization_name,
            role=self.desired_role,
        )

        assert result == {
            "username": self.user.username,
            "submitter": self.initiator_user.username,
            "organization_name": self.organization_name,
            "role": self.desired_role,
        }
        subject_renderer.assert_(**result)
        body_renderer.assert_(**result)
        html_renderer.assert_(**result)
        assert db_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{self.initiator_user.name} <{self.initiator_user.email}>",
                {
                    "subject": subject_renderer.string_response,
                    "body_text": body_renderer.string_response,
                    "body_html": (
                        f"<html>\n"
                        f"<head></head>\n"
                        f"<body><p>{html_renderer.string_response}</p></body>\n"
                        f"</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": self.initiator_user.id,
                    "additional": {
                        "from_": db_request.registry.settings["mail.sender"],
                        "to": self.initiator_user.email,
                        "subject": subject_renderer.string_response,
                        "redact_ip": False,
                    },
                },
            )
        ]

    def test_send_role_changed_as_organization_email(
        self,
        db_request,
        organization_invite,
        make_email_renderers,
        send_email,
    ):
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "role-changed-as-organization-member"
        )

        result = email.send_role_changed_as_organization_member_email(
            db_request,
            self.user,
            submitter=self.initiator_user,
            organization_name=self.organization_name,
            role=self.desired_role,
        )

        assert result == {
            "username": self.user.username,
            "submitter": self.initiator_user.username,
            "organization_name": self.organization_name,
            "role": self.desired_role,
        }
        subject_renderer.assert_(**result)
        body_renderer.assert_(**result)
        html_renderer.assert_(**result)
        assert db_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{self.user.name} <{self.user.email}>",
                {
                    "subject": subject_renderer.string_response,
                    "body_text": body_renderer.string_response,
                    "body_html": (
                        f"<html>\n"
                        f"<head></head>\n"
                        f"<body><p>{html_renderer.string_response}</p></body>\n"
                        f"</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": self.user.id,
                    "additional": {
                        "from_": db_request.registry.settings["mail.sender"],
                        "to": self.user.email,
                        "subject": subject_renderer.string_response,
                        "redact_ip": True,
                    },
                },
            )
        ]


class TestOrganizationUpdateEmails:
    @pytest.fixture
    def organization_update(self, pyramid_user):
        self.user = UserFactory.create()
        EmailFactory.create(user=self.user, verified=True)
        self.organization_name = "example"
        self.organization_display_name = "Example"
        self.organization_link_url = "https://www.example.com/"
        self.organization_description = "An example organization for testing"
        self.organization_orgtype = "Company"
        self.previous_organization_display_name = "Example Group"
        self.previous_organization_link_url = "https://www.example.com/group/"
        self.previous_organization_description = "An example group for testing"
        self.previous_organization_orgtype = "Community"

    def test_send_organization_renamed_email(
        self,
        db_request,
        organization_update,
        make_email_renderers,
        send_email,
    ):
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "organization-updated"
        )

        result = email.send_organization_updated_email(
            db_request,
            self.user,
            organization_name=self.organization_name,
            organization_display_name=self.organization_display_name,
            organization_link_url=self.organization_link_url,
            organization_description=self.organization_description,
            organization_orgtype=self.organization_orgtype,
            previous_organization_display_name=self.previous_organization_display_name,
            previous_organization_link_url=self.previous_organization_link_url,
            previous_organization_description=self.previous_organization_description,
            previous_organization_orgtype=self.previous_organization_orgtype,
        )

        assert result == {
            "organization_name": self.organization_name,
            "organization_display_name": self.organization_display_name,
            "organization_link_url": self.organization_link_url,
            "organization_description": self.organization_description,
            "organization_orgtype": self.organization_orgtype,
            "previous_organization_display_name": (
                self.previous_organization_display_name
            ),
            "previous_organization_link_url": self.previous_organization_link_url,
            "previous_organization_description": self.previous_organization_description,
            "previous_organization_orgtype": self.previous_organization_orgtype,
        }
        subject_renderer.assert_(**result)
        body_renderer.assert_(**result)
        html_renderer.assert_(**result)
        assert db_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{self.user.name} <{self.user.email}>",
                {
                    "subject": subject_renderer.string_response,
                    "body_text": body_renderer.string_response,
                    "body_html": (
                        f"<html>\n"
                        f"<head></head>\n"
                        f"<body><p>{html_renderer.string_response}</p></body>\n"
                        f"</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": self.user.id,
                    "additional": {
                        "from_": db_request.registry.settings["mail.sender"],
                        "to": self.user.email,
                        "subject": subject_renderer.string_response,
                        "redact_ip": True,
                    },
                },
            )
        ]


class TestOrganizationRenameEmails:
    @pytest.fixture
    def organization_rename(self, pyramid_user):
        self.user = UserFactory.create()
        EmailFactory.create(user=self.user, verified=True)
        self.organization_name = "example"
        self.previous_organization_name = "examplegroup"

    def test_send_admin_organization_renamed_email(
        self,
        db_request,
        organization_rename,
        make_email_renderers,
        send_email,
    ):
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "admin-organization-renamed"
        )

        result = email.send_admin_organization_renamed_email(
            db_request,
            self.user,
            organization_name=self.organization_name,
            previous_organization_name=self.previous_organization_name,
        )

        assert result == {
            "organization_name": self.organization_name,
            "previous_organization_name": self.previous_organization_name,
        }
        subject_renderer.assert_(**result)
        body_renderer.assert_(**result)
        html_renderer.assert_(**result)
        assert db_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{self.user.name} <{self.user.email}>",
                {
                    "subject": subject_renderer.string_response,
                    "body_text": body_renderer.string_response,
                    "body_html": (
                        f"<html>\n"
                        f"<head></head>\n"
                        f"<body><p>{html_renderer.string_response}</p></body>\n"
                        f"</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": self.user.id,
                    "additional": {
                        "from_": db_request.registry.settings["mail.sender"],
                        "to": self.user.email,
                        "subject": subject_renderer.string_response,
                        "redact_ip": True,
                    },
                },
            )
        ]

    def test_send_organization_renamed_email(
        self,
        db_request,
        organization_rename,
        make_email_renderers,
        send_email,
    ):
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "organization-renamed"
        )

        result = email.send_organization_renamed_email(
            db_request,
            self.user,
            organization_name=self.organization_name,
            previous_organization_name=self.previous_organization_name,
        )

        assert result == {
            "organization_name": self.organization_name,
            "previous_organization_name": self.previous_organization_name,
        }
        subject_renderer.assert_(**result)
        body_renderer.assert_(**result)
        html_renderer.assert_(**result)
        assert db_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{self.user.name} <{self.user.email}>",
                {
                    "subject": subject_renderer.string_response,
                    "body_text": body_renderer.string_response,
                    "body_html": (
                        f"<html>\n"
                        f"<head></head>\n"
                        f"<body><p>{html_renderer.string_response}</p></body>\n"
                        f"</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": self.user.id,
                    "additional": {
                        "from_": db_request.registry.settings["mail.sender"],
                        "to": self.user.email,
                        "subject": subject_renderer.string_response,
                        "redact_ip": True,
                    },
                },
            )
        ]


class TestOrganizationDeleteEmails:
    @pytest.fixture
    def organization_delete(self, pyramid_user):
        self.user = UserFactory.create()
        EmailFactory.create(user=self.user, verified=True)
        self.organization_name = "example"

    def test_send_admin_organization_deleted_email(
        self,
        db_request,
        organization_delete,
        make_email_renderers,
        send_email,
    ):
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "admin-organization-deleted"
        )

        result = email.send_admin_organization_deleted_email(
            db_request,
            self.user,
            organization_name=self.organization_name,
        )

        assert result == {
            "organization_name": self.organization_name,
        }
        subject_renderer.assert_(**result)
        body_renderer.assert_(**result)
        html_renderer.assert_(**result)
        assert db_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{self.user.name} <{self.user.email}>",
                {
                    "subject": subject_renderer.string_response,
                    "body_text": body_renderer.string_response,
                    "body_html": (
                        f"<html>\n"
                        f"<head></head>\n"
                        f"<body><p>{html_renderer.string_response}</p></body>\n"
                        f"</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": self.user.id,
                    "additional": {
                        "from_": db_request.registry.settings["mail.sender"],
                        "to": self.user.email,
                        "subject": subject_renderer.string_response,
                        "redact_ip": True,
                    },
                },
            )
        ]

    def test_send_organization_deleted_email(
        self,
        db_request,
        organization_delete,
        make_email_renderers,
        send_email,
    ):
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "organization-deleted"
        )

        result = email.send_organization_deleted_email(
            db_request,
            self.user,
            organization_name=self.organization_name,
        )

        assert result == {
            "organization_name": self.organization_name,
        }
        subject_renderer.assert_(**result)
        body_renderer.assert_(**result)
        html_renderer.assert_(**result)
        assert db_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{self.user.name} <{self.user.email}>",
                {
                    "subject": subject_renderer.string_response,
                    "body_text": body_renderer.string_response,
                    "body_html": (
                        f"<html>\n"
                        f"<head></head>\n"
                        f"<body><p>{html_renderer.string_response}</p></body>\n"
                        f"</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": self.user.id,
                    "additional": {
                        "from_": db_request.registry.settings["mail.sender"],
                        "to": self.user.email,
                        "subject": subject_renderer.string_response,
                        "redact_ip": True,
                    },
                },
            )
        ]


class TestTeamMemberEmails:
    @pytest.fixture
    def team(self, pyramid_user):
        self.user = UserFactory.create()
        EmailFactory.create(user=self.user, verified=True)
        self.submitter = pyramid_user
        self.organization_name = "exampleorganization"
        self.team_name = "Example Team"

    @pytest.mark.parametrize(
        ("email_template_name", "send_team_member_email"),
        [
            ("added-as-team-member", email.send_added_as_team_member_email),
            ("removed-as-team-member", email.send_removed_as_team_member_email),
            ("team-member-added", email.send_team_member_added_email),
            ("team-member-removed", email.send_team_member_removed_email),
        ],
    )
    def test_send_team_member_email(
        self,
        db_request,
        team,
        make_email_renderers,
        send_email,
        email_template_name,
        send_team_member_email,
    ):
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            email_template_name
        )

        if email_template_name.endswith("-as-team-member"):
            recipient = self.user
            result = send_team_member_email(
                db_request,
                self.user,
                submitter=self.submitter,
                organization_name=self.organization_name,
                team_name=self.team_name,
            )
        else:
            recipient = self.submitter
            result = send_team_member_email(
                db_request,
                self.submitter,
                user=self.user,
                submitter=self.submitter,
                organization_name=self.organization_name,
                team_name=self.team_name,
            )

        assert result == {
            "username": self.user.username,
            "submitter": self.submitter.username,
            "organization_name": self.organization_name,
            "team_name": self.team_name,
        }
        subject_renderer.assert_(**result)
        body_renderer.assert_(**result)
        html_renderer.assert_(**result)
        assert db_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{recipient.name} <{recipient.email}>",
                {
                    "subject": subject_renderer.string_response,
                    "body_text": body_renderer.string_response,
                    "body_html": (
                        f"<html>\n"
                        f"<head></head>\n"
                        f"<body><p>{html_renderer.string_response}</p></body>\n"
                        f"</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": recipient.id,
                    "additional": {
                        "from_": db_request.registry.settings["mail.sender"],
                        "to": recipient.email,
                        "subject": subject_renderer.string_response,
                        "redact_ip": recipient != self.submitter,
                    },
                },
            )
        ]


class TestTeamEmails:
    @pytest.fixture
    def team(self, pyramid_user):
        self.user = pyramid_user
        self.organization_name = "exampleorganization"
        self.team_name = "Example Team"

    @pytest.mark.parametrize(
        ("email_template_name", "send_team_email"),
        [
            ("team-created", email.send_team_created_email),
            ("team-deleted", email.send_team_deleted_email),
        ],
    )
    def test_send_team_email(
        self,
        db_request,
        team,
        make_email_renderers,
        send_email,
        email_template_name,
        send_team_email,
    ):
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            email_template_name
        )

        result = send_team_email(
            db_request,
            self.user,
            organization_name=self.organization_name,
            team_name=self.team_name,
        )

        assert result == {
            "organization_name": self.organization_name,
            "team_name": self.team_name,
        }
        subject_renderer.assert_(**result)
        body_renderer.assert_(**result)
        html_renderer.assert_(**result)
        assert db_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{self.user.name} <{self.user.email}>",
                {
                    "subject": subject_renderer.string_response,
                    "body_text": body_renderer.string_response,
                    "body_html": (
                        f"<html>\n"
                        f"<head></head>\n"
                        f"<body><p>{html_renderer.string_response}</p></body>\n"
                        f"</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": self.user.id,
                    "additional": {
                        "from_": db_request.registry.settings["mail.sender"],
                        "to": self.user.email,
                        "subject": subject_renderer.string_response,
                        "redact_ip": False,
                    },
                },
            )
        ]


class TestCollaboratorAddedEmail:
    def test_collaborator_added_email(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        stub_user = pretend.stub(
            id="id_1",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        stub_submitter_user = pretend.stub(
            id="id_2",
            username="submitterusername",
            name="",
            email="submiteremail@example.com",
            primary_email=pretend.stub(
                email="submiteremail@example.com", verified=True
            ),
        )
        subject_renderer = pyramid_config.testing_add_renderer(
            "email/collaborator-added/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/collaborator-added/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/collaborator-added/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        ids = [stub_submitter_user.id, stub_user.id]
        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=ids.pop())
                )
            ),
        )
        pyramid_request.user = stub_submitter_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        result = email.send_collaborator_added_email(
            pyramid_request,
            [stub_user, stub_submitter_user],
            user=stub_user,
            submitter=stub_submitter_user,
            project_name="test_project",
            role="Owner",
        )

        assert result == {
            "username": stub_user.username,
            "project": "test_project",
            "role": "Owner",
            "submitter": stub_submitter_user.username,
        }
        subject_renderer.assert_()
        body_renderer.assert_(username=stub_user.username)
        body_renderer.assert_(project="test_project")
        body_renderer.assert_(role="Owner")
        body_renderer.assert_(submitter=stub_submitter_user.username)
        html_renderer.assert_(username=stub_user.username)
        html_renderer.assert_(project="test_project")
        html_renderer.assert_(role="Owner")
        html_renderer.assert_(submitter=stub_submitter_user.username)

        assert pyramid_request.task.calls == [
            pretend.call(send_email),
            pretend.call(send_email),
        ]
        assert send_email.delay.calls == [
            pretend.call(
                "username <email@example.com>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "email@example.com",
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
            pretend.call(
                "submitterusername <submiteremail@example.com>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_submitter_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "submiteremail@example.com",
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            ),
        ]

    def test_collaborator_added_email_unverified(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        stub_user = pretend.stub(
            id="id_1",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=False),
        )
        stub_submitter_user = pretend.stub(
            id="id_2",
            username="submitterusername",
            name="",
            email="submiteremail@example.com",
            primary_email=pretend.stub(
                email="submiteremail@example.com", verified=True
            ),
        )
        subject_renderer = pyramid_config.testing_add_renderer(
            "email/collaborator-added/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/collaborator-added/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/collaborator-added/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=stub_submitter_user.id)
                )
            ),
        )
        pyramid_request.user = stub_submitter_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        result = email.send_collaborator_added_email(
            pyramid_request,
            [stub_user, stub_submitter_user],
            user=stub_user,
            submitter=stub_submitter_user,
            project_name="test_project",
            role="Owner",
        )

        assert result == {
            "username": stub_user.username,
            "project": "test_project",
            "role": "Owner",
            "submitter": stub_submitter_user.username,
        }
        subject_renderer.assert_()
        body_renderer.assert_(username=stub_user.username)
        body_renderer.assert_(project="test_project")
        body_renderer.assert_(role="Owner")
        body_renderer.assert_(submitter=stub_submitter_user.username)
        html_renderer.assert_(username=stub_user.username)
        html_renderer.assert_(project="test_project")
        html_renderer.assert_(role="Owner")
        html_renderer.assert_(submitter=stub_submitter_user.username)

        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                "submitterusername <submiteremail@example.com>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_submitter_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "submiteremail@example.com",
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            )
        ]


class TestProjectRoleVerificationEmail:
    def test_project_role_verification_email(
        self, db_request, pyramid_config, token_service, monkeypatch
    ):
        stub_user = UserFactory.create()
        EmailFactory.create(
            email="email@example.com",
            primary=True,
            verified=True,
            public=True,
            user=stub_user,
        )

        subject_renderer = pyramid_config.testing_add_renderer(
            "email/verify-project-role/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/verify-project-role/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/verify-project-role/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        db_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        db_request.user = stub_user
        db_request.registry.settings = {"mail.sender": "noreply@example.com"}
        monkeypatch.setattr(email, "send_email", send_email)

        result = email.send_project_role_verification_email(
            db_request,
            stub_user,
            desired_role="Maintainer",
            initiator_username="initiating_user",
            project_name="project_name",
            email_token="TOKEN",
            token_age=token_service.max_age,
        )

        assert result == {
            "desired_role": "Maintainer",
            "email_address": stub_user.email,
            "initiator_username": "initiating_user",
            "n_hours": token_service.max_age // 60 // 60,
            "project_name": "project_name",
            "token": "TOKEN",
        }
        subject_renderer.assert_()
        body_renderer.assert_(token="TOKEN", email_address=stub_user.email)
        html_renderer.assert_(token="TOKEN", email_address=stub_user.email)
        assert db_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{stub_user.name} <{stub_user.email}>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "email@example.com",
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            )
        ]


class TestAddedAsCollaboratorEmail:
    def test_added_as_collaborator_email(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        stub_user = pretend.stub(
            id="id_1",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        stub_submitter_user = pretend.stub(
            id="id_2", username="submitterusername", email="submiteremail"
        )
        subject_renderer = pyramid_config.testing_add_renderer(
            "email/added-as-collaborator/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/added-as-collaborator/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/added-as-collaborator/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=stub_user.id)
                )
            ),
        )
        pyramid_request.user = stub_submitter_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        result = email.send_added_as_collaborator_email(
            pyramid_request,
            stub_user,
            submitter=stub_submitter_user,
            project_name="test_project",
            role="Owner",
        )

        assert result == {
            "project_name": "test_project",
            "role": "Owner",
            "initiator_username": stub_submitter_user.username,
        }
        subject_renderer.assert_()
        body_renderer.assert_(initiator_username=stub_submitter_user.username)
        body_renderer.assert_(project_name="test_project")
        body_renderer.assert_(role="Owner")
        html_renderer.assert_(initiator_username=stub_submitter_user.username)
        html_renderer.assert_(project_name="test_project")
        html_renderer.assert_(role="Owner")

        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                "username <email@example.com>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "email@example.com",
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            )
        ]

    def test_added_as_collaborator_email_unverified(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        stub_user = pretend.stub(
            id="id_1",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=False),
        )
        stub_submitter_user = pretend.stub(
            id="id_2", username="submitterusername", email="submiteremail"
        )
        subject_renderer = pyramid_config.testing_add_renderer(
            "email/added-as-collaborator/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/added-as-collaborator/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/added-as-collaborator/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=stub_user.id)
                )
            ),
        )
        pyramid_request.user = stub_submitter_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        result = email.send_added_as_collaborator_email(
            pyramid_request,
            stub_user,
            submitter=stub_submitter_user,
            project_name="test_project",
            role="Owner",
        )

        assert result == {
            "project_name": "test_project",
            "role": "Owner",
            "initiator_username": stub_submitter_user.username,
        }
        subject_renderer.assert_()
        body_renderer.assert_(initiator_username=stub_submitter_user.username)
        body_renderer.assert_(project_name="test_project")
        body_renderer.assert_(role="Owner")
        html_renderer.assert_(initiator_username=stub_submitter_user.username)
        html_renderer.assert_(project_name="test_project")
        html_renderer.assert_(role="Owner")

        assert pyramid_request.task.calls == []
        assert send_email.delay.calls == []


class TestCollaboratorRemovedEmail:
    def test_collaborator_removed_email(self, db_request, pyramid_config, monkeypatch):
        removed_user = UserFactory.create()
        EmailFactory.create(primary=True, verified=True, public=True, user=removed_user)
        submitter_user = UserFactory.create()
        EmailFactory.create(
            primary=True, verified=True, public=True, user=submitter_user
        )
        db_request.user = submitter_user

        subject_renderer = pyramid_config.testing_add_renderer(
            "email/collaborator-removed/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/collaborator-removed/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/collaborator-removed/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        db_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        result = email.send_collaborator_removed_email(
            db_request,
            [removed_user, submitter_user],
            user=removed_user,
            submitter=submitter_user,
            project_name="test_project",
        )

        assert result == {
            "username": removed_user.username,
            "project": "test_project",
            "submitter": submitter_user.username,
        }
        subject_renderer.assert_()
        body_renderer.assert_(username=removed_user.username)
        body_renderer.assert_(project="test_project")
        body_renderer.assert_(submitter=submitter_user.username)
        html_renderer.assert_(username=removed_user.username)
        html_renderer.assert_(project="test_project")
        html_renderer.assert_(submitter=submitter_user.username)

        assert db_request.task.calls == [
            pretend.call(send_email),
            pretend.call(send_email),
        ]
        assert send_email.delay.calls == [
            pretend.call(
                f"{removed_user.name} <{removed_user.primary_email.email}>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": removed_user.id,
                    "additional": {
                        "from_": None,
                        "to": removed_user.primary_email.email,
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
            pretend.call(
                f"{submitter_user.name} <{submitter_user.primary_email.email}>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": submitter_user.id,
                    "additional": {
                        "from_": None,
                        "to": submitter_user.primary_email.email,
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            ),
        ]


class TestRemovedAsCollaboratorEmail:
    def test_removed_as_collaborator_email(
        self, db_request, pyramid_config, monkeypatch
    ):
        removed_user = UserFactory.create()
        EmailFactory.create(primary=True, verified=True, public=True, user=removed_user)
        submitter_user = UserFactory.create()
        EmailFactory.create(
            primary=True, verified=True, public=True, user=submitter_user
        )
        db_request.user = submitter_user

        subject_renderer = pyramid_config.testing_add_renderer(
            "email/removed-as-collaborator/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/removed-as-collaborator/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/removed-as-collaborator/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        db_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        result = email.send_removed_as_collaborator_email(
            db_request,
            removed_user,
            submitter=submitter_user,
            project_name="test_project",
        )

        assert result == {
            "project": "test_project",
            "submitter": submitter_user.username,
        }
        subject_renderer.assert_()
        body_renderer.assert_(submitter=submitter_user.username)
        body_renderer.assert_(project="test_project")
        html_renderer.assert_(submitter=submitter_user.username)
        html_renderer.assert_(project="test_project")

        assert db_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{removed_user.name} <{removed_user.primary_email.email}>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": removed_user.id,
                    "additional": {
                        "from_": None,
                        "to": removed_user.primary_email.email,
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            )
        ]


class TestRoleChangedEmail:
    def test_role_changed_email(self, db_request, pyramid_config, monkeypatch):
        changed_user = UserFactory.create()
        EmailFactory.create(primary=True, verified=True, public=True, user=changed_user)
        submitter_user = UserFactory.create()
        EmailFactory.create(
            primary=True, verified=True, public=True, user=submitter_user
        )
        db_request.user = submitter_user

        subject_renderer = pyramid_config.testing_add_renderer(
            "email/collaborator-role-changed/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/collaborator-role-changed/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/collaborator-role-changed/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        db_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        result = email.send_collaborator_role_changed_email(
            db_request,
            [changed_user, submitter_user],
            user=changed_user,
            submitter=submitter_user,
            project_name="test_project",
            role="Owner",
        )

        assert result == {
            "username": changed_user.username,
            "project": "test_project",
            "role": "Owner",
            "submitter": submitter_user.username,
        }
        subject_renderer.assert_()
        body_renderer.assert_(username=changed_user.username)
        body_renderer.assert_(project="test_project")
        body_renderer.assert_(role="Owner")
        body_renderer.assert_(submitter=submitter_user.username)
        html_renderer.assert_(username=changed_user.username)
        html_renderer.assert_(project="test_project")
        html_renderer.assert_(role="Owner")
        html_renderer.assert_(submitter=submitter_user.username)

        assert db_request.task.calls == [
            pretend.call(send_email),
            pretend.call(send_email),
        ]
        assert send_email.delay.calls == [
            pretend.call(
                f"{changed_user.name} <{changed_user.primary_email.email}>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": changed_user.id,
                    "additional": {
                        "from_": None,
                        "to": changed_user.primary_email.email,
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
            pretend.call(
                f"{submitter_user.name} <{submitter_user.primary_email.email}>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": submitter_user.id,
                    "additional": {
                        "from_": None,
                        "to": submitter_user.primary_email.email,
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            ),
        ]


class TestRoleChangedAsCollaboratorEmail:
    def test_role_changed_as_collaborator_email(
        self, db_request, pyramid_config, monkeypatch
    ):
        changed_user = UserFactory.create()
        EmailFactory.create(primary=True, verified=True, public=True, user=changed_user)
        submitter_user = UserFactory.create()
        EmailFactory.create(
            primary=True, verified=True, public=True, user=submitter_user
        )
        db_request.user = submitter_user

        subject_renderer = pyramid_config.testing_add_renderer(
            "email/role-changed-as-collaborator/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/role-changed-as-collaborator/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/role-changed-as-collaborator/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        db_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        result = email.send_role_changed_as_collaborator_email(
            db_request,
            changed_user,
            submitter=submitter_user,
            project_name="test_project",
            role="Owner",
        )

        assert result == {
            "project": "test_project",
            "role": "Owner",
            "submitter": submitter_user.username,
        }
        subject_renderer.assert_()
        body_renderer.assert_(submitter=submitter_user.username)
        body_renderer.assert_(project="test_project")
        body_renderer.assert_(role="Owner")
        html_renderer.assert_(submitter=submitter_user.username)
        html_renderer.assert_(project="test_project")
        html_renderer.assert_(role="Owner")

        assert db_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{changed_user.name} <{changed_user.primary_email.email}>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": changed_user.id,
                    "additional": {
                        "from_": None,
                        "to": changed_user.primary_email.email,
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
        ]


class TestTeamCollaboratorEmails:
    @pytest.fixture
    def team(self, pyramid_user):
        self.user = UserFactory.create()
        EmailFactory.create(user=self.user, verified=True)
        self.submitter = pyramid_user
        self.team = TeamFactory.create(name="Example Team")
        self.project_name = "exampleproject"
        self.role = "Admin"

    @pytest.mark.parametrize(
        ("email_template_name", "send_team_collaborator_email"),
        [
            ("added-as-team-collaborator", email.send_added_as_team_collaborator_email),
            (
                "removed-as-team-collaborator",
                email.send_removed_as_team_collaborator_email,
            ),
            (
                "role-changed-as-team-collaborator",
                email.send_role_changed_as_team_collaborator_email,
            ),
            ("team-collaborator-added", email.send_team_collaborator_added_email),
            ("team-collaborator-removed", email.send_team_collaborator_removed_email),
            (
                "team-collaborator-role-changed",
                email.send_team_collaborator_role_changed_email,
            ),
        ],
    )
    def test_send_team_collaborator_email(
        self,
        db_request,
        team,
        make_email_renderers,
        send_email,
        email_template_name,
        send_team_collaborator_email,
    ):
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            email_template_name
        )

        if "removed" in email_template_name:
            result = send_team_collaborator_email(
                db_request,
                self.user,
                team=self.team,
                submitter=self.submitter,
                project_name=self.project_name,
            )
        else:
            result = send_team_collaborator_email(
                db_request,
                self.user,
                team=self.team,
                submitter=self.submitter,
                project_name=self.project_name,
                role=self.role,
            )

        if "removed" in email_template_name:
            assert result == {
                "team_name": self.team.name,
                "project": self.project_name,
                "submitter": self.submitter.username,
            }
        else:
            assert result == {
                "team_name": self.team.name,
                "project": self.project_name,
                "submitter": self.submitter.username,
                "role": self.role,
            }
        subject_renderer.assert_(**result)
        body_renderer.assert_(**result)
        html_renderer.assert_(**result)
        assert db_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{self.user.name} <{self.user.email}>",
                {
                    "subject": subject_renderer.string_response,
                    "body_text": body_renderer.string_response,
                    "body_html": (
                        f"<html>\n"
                        f"<head></head>\n"
                        f"<body><p>{html_renderer.string_response}</p></body>\n"
                        f"</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": self.user.id,
                    "additional": {
                        "from_": db_request.registry.settings["mail.sender"],
                        "to": self.user.email,
                        "subject": subject_renderer.string_response,
                        "redact_ip": True,
                    },
                },
            )
        ]


class TestRemovedProjectEmail:
    def test_removed_project_email_to_maintainer(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        stub_user = pretend.stub(
            id="id_1",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        stub_submitter_user = pretend.stub(
            id="id_2",
            username="submitterusername",
            name="",
            email="submiteremail@example.com",
            primary_email=pretend.stub(
                email="submiteremail@example.com", verified=True
            ),
        )
        subject_renderer = pyramid_config.testing_add_renderer(
            "email/removed-project/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/removed-project/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/removed-project/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        ids = [stub_submitter_user.id, stub_user.id]
        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=ids.pop())
                )
            ),
        )
        pyramid_request.user = stub_submitter_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        result = email.send_removed_project_email(
            pyramid_request,
            [stub_user, stub_submitter_user],
            project_name="test_project",
            submitter_name=stub_submitter_user.username,
            submitter_role="Owner",
            recipient_role="Maintainer",
        )

        assert result == {
            "project_name": "test_project",
            "submitter_name": stub_submitter_user.username,
            "submitter_role": "owner",
            "recipient_role_descr": "a maintainer",
        }

        subject_renderer.assert_(project_name="test_project")
        body_renderer.assert_(project_name="test_project")
        body_renderer.assert_(submitter_name=stub_submitter_user.username)
        body_renderer.assert_(submitter_role="owner")
        body_renderer.assert_(recipient_role_descr="a maintainer")

        assert pyramid_request.task.calls == [
            pretend.call(send_email),
            pretend.call(send_email),
        ]

        assert send_email.delay.calls == [
            pretend.call(
                "username <email@example.com>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "email@example.com",
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
            pretend.call(
                "submitterusername <submiteremail@example.com>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_submitter_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "submiteremail@example.com",
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            ),
        ]

    def test_removed_project_email_to_owner(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        stub_user = pretend.stub(
            id="id_1",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        stub_submitter_user = pretend.stub(
            id="id_2",
            username="submitterusername",
            name="",
            email="submiteremail@example.com",
            primary_email=pretend.stub(
                email="submiteremail@example.com", verified=True
            ),
        )
        subject_renderer = pyramid_config.testing_add_renderer(
            "email/removed-project/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/removed-project/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/removed-project/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        ids = [stub_submitter_user.id, stub_user.id]
        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=ids.pop())
                )
            ),
        )
        pyramid_request.user = stub_submitter_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        result = email.send_removed_project_email(
            pyramid_request,
            [stub_user, stub_submitter_user],
            project_name="test_project",
            submitter_name=stub_submitter_user.username,
            submitter_role="Owner",
            recipient_role="Owner",
        )

        assert result == {
            "project_name": "test_project",
            "submitter_name": stub_submitter_user.username,
            "submitter_role": "owner",
            "recipient_role_descr": "an owner",
        }

        subject_renderer.assert_(project_name="test_project")
        body_renderer.assert_(project_name="test_project")
        body_renderer.assert_(submitter_name=stub_submitter_user.username)
        body_renderer.assert_(submitter_role="owner")
        body_renderer.assert_(recipient_role_descr="an owner")

        assert pyramid_request.task.calls == [
            pretend.call(send_email),
            pretend.call(send_email),
        ]

        assert send_email.delay.calls == [
            pretend.call(
                "username <email@example.com>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "email@example.com",
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
            pretend.call(
                "submitterusername <submiteremail@example.com>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_submitter_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "submiteremail@example.com",
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            ),
        ]


class TestYankedReleaseEmail:
    def test_send_yanked_project_release_email_to_maintainer(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        stub_user = pretend.stub(
            id="id_1",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        stub_submitter_user = pretend.stub(
            id="id_2",
            username="submitterusername",
            name="",
            email="submiteremail@example.com",
            primary_email=pretend.stub(
                email="submiteremail@example.com", verified=True
            ),
        )

        subject_renderer = pyramid_config.testing_add_renderer(
            "email/yanked-project-release/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/yanked-project-release/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/yanked-project-release/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        ids = [stub_submitter_user.id, stub_user.id]
        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=ids.pop())
                )
            ),
        )
        pyramid_request.user = stub_submitter_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        release = pretend.stub(
            version="0.0.0",
            project=pretend.stub(name="test_project"),
            created=datetime.datetime(2017, 2, 5, 0, 0, 0, 0),
            yanked_reason="Yanky Doodle went to town",
        )

        result = email.send_yanked_project_release_email(
            pyramid_request,
            [stub_user, stub_submitter_user],
            release=release,
            submitter_name=stub_submitter_user.username,
            submitter_role="Owner",
            recipient_role="Maintainer",
        )

        assert result == {
            "project": release.project.name,
            "release": release.version,
            "release_date": release.created.strftime("%Y-%m-%d"),
            "submitter": stub_submitter_user.username,
            "submitter_role": "owner",
            "recipient_role_descr": "a maintainer",
            "yanked_reason": "Yanky Doodle went to town",
        }

        subject_renderer.assert_(project="test_project")
        subject_renderer.assert_(release="0.0.0")
        body_renderer.assert_(project="test_project")
        body_renderer.assert_(release="0.0.0")
        body_renderer.assert_(release_date=release.created.strftime("%Y-%m-%d"))
        body_renderer.assert_(submitter=stub_submitter_user.username)
        body_renderer.assert_(submitter_role="owner")
        body_renderer.assert_(recipient_role_descr="a maintainer")

        assert pyramid_request.task.calls == [
            pretend.call(send_email),
            pretend.call(send_email),
        ]

        assert send_email.delay.calls == [
            pretend.call(
                "username <email@example.com>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "email@example.com",
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
            pretend.call(
                "submitterusername <submiteremail@example.com>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_submitter_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "submiteremail@example.com",
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            ),
        ]

    def test_send_yanked_project_release_email_to_owner(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        stub_user = pretend.stub(
            id="id_1",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        stub_submitter_user = pretend.stub(
            id="id_2",
            username="submitterusername",
            name="",
            email="submiteremail@example.com",
            primary_email=pretend.stub(
                email="submiteremail@example.com", verified=True
            ),
        )

        subject_renderer = pyramid_config.testing_add_renderer(
            "email/yanked-project-release/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/yanked-project-release/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/yanked-project-release/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        ids = [stub_submitter_user.id, stub_user.id]
        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=ids.pop())
                )
            ),
        )
        pyramid_request.user = stub_submitter_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        release = pretend.stub(
            version="0.0.0",
            project=pretend.stub(name="test_project"),
            created=datetime.datetime(2017, 2, 5, 0, 0, 0, 0),
            yanked_reason="Yanky Doodle went to town",
        )

        result = email.send_yanked_project_release_email(
            pyramid_request,
            [stub_user, stub_submitter_user],
            release=release,
            submitter_name=stub_submitter_user.username,
            submitter_role="Owner",
            recipient_role="Owner",
        )

        assert result == {
            "project": release.project.name,
            "release": release.version,
            "release_date": release.created.strftime("%Y-%m-%d"),
            "submitter": stub_submitter_user.username,
            "submitter_role": "owner",
            "recipient_role_descr": "an owner",
            "yanked_reason": "Yanky Doodle went to town",
        }

        subject_renderer.assert_(project="test_project")
        subject_renderer.assert_(release="0.0.0")
        body_renderer.assert_(project="test_project")
        body_renderer.assert_(release="0.0.0")
        body_renderer.assert_(release_date=release.created.strftime("%Y-%m-%d"))
        body_renderer.assert_(submitter=stub_submitter_user.username)
        body_renderer.assert_(submitter_role="owner")
        body_renderer.assert_(recipient_role_descr="an owner")

        assert pyramid_request.task.calls == [
            pretend.call(send_email),
            pretend.call(send_email),
        ]

        assert send_email.delay.calls == [
            pretend.call(
                "username <email@example.com>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "email@example.com",
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
            pretend.call(
                "submitterusername <submiteremail@example.com>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_submitter_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "submiteremail@example.com",
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            ),
        ]


class TestUnyankedReleaseEmail:
    def test_send_unyanked_project_release_email_to_maintainer(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        stub_user = pretend.stub(
            id="id_1",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        stub_submitter_user = pretend.stub(
            id="id_2",
            username="submitterusername",
            name="",
            email="submiteremail@example.com",
            primary_email=pretend.stub(
                email="submiteremail@example.com", verified=True
            ),
        )

        subject_renderer = pyramid_config.testing_add_renderer(
            "email/unyanked-project-release/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/unyanked-project-release/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/unyanked-project-release/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        ids = [stub_submitter_user.id, stub_user.id]
        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=ids.pop())
                )
            ),
        )
        pyramid_request.user = stub_submitter_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        release = pretend.stub(
            version="0.0.0",
            project=pretend.stub(name="test_project"),
            created=datetime.datetime(2017, 2, 5, 0, 0, 0, 0),
            yanked_reason="",
        )

        result = email.send_unyanked_project_release_email(
            pyramid_request,
            [stub_user, stub_submitter_user],
            release=release,
            submitter_name=stub_submitter_user.username,
            submitter_role="Owner",
            recipient_role="Maintainer",
        )

        assert result == {
            "project": release.project.name,
            "release": release.version,
            "release_date": release.created.strftime("%Y-%m-%d"),
            "submitter": stub_submitter_user.username,
            "submitter_role": "owner",
            "recipient_role_descr": "a maintainer",
        }

        subject_renderer.assert_(project="test_project")
        subject_renderer.assert_(release="0.0.0")
        body_renderer.assert_(project="test_project")
        body_renderer.assert_(release="0.0.0")
        body_renderer.assert_(release_date=release.created.strftime("%Y-%m-%d"))
        body_renderer.assert_(submitter=stub_submitter_user.username)
        body_renderer.assert_(submitter_role="owner")
        body_renderer.assert_(recipient_role_descr="a maintainer")

        assert pyramid_request.task.calls == [
            pretend.call(send_email),
            pretend.call(send_email),
        ]

        assert send_email.delay.calls == [
            pretend.call(
                "username <email@example.com>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "email@example.com",
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
            pretend.call(
                "submitterusername <submiteremail@example.com>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_submitter_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "submiteremail@example.com",
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            ),
        ]

    def test_send_unyanked_project_release_email_to_owner(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        stub_user = pretend.stub(
            id="id_1",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        stub_submitter_user = pretend.stub(
            id="id_2",
            username="submitterusername",
            name="",
            email="submiteremail@example.com",
            primary_email=pretend.stub(
                email="submiteremail@example.com", verified=True
            ),
        )

        subject_renderer = pyramid_config.testing_add_renderer(
            "email/unyanked-project-release/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/unyanked-project-release/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/unyanked-project-release/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        ids = [stub_submitter_user.id, stub_user.id]
        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=ids.pop())
                )
            ),
        )
        pyramid_request.user = stub_submitter_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        release = pretend.stub(
            version="0.0.0",
            project=pretend.stub(name="test_project"),
            created=datetime.datetime(2017, 2, 5, 0, 0, 0, 0),
            yanked_reason="",
        )

        result = email.send_unyanked_project_release_email(
            pyramid_request,
            [stub_user, stub_submitter_user],
            release=release,
            submitter_name=stub_submitter_user.username,
            submitter_role="Owner",
            recipient_role="Owner",
        )

        assert result == {
            "project": release.project.name,
            "release": release.version,
            "release_date": release.created.strftime("%Y-%m-%d"),
            "submitter": stub_submitter_user.username,
            "submitter_role": "owner",
            "recipient_role_descr": "an owner",
        }

        subject_renderer.assert_(project="test_project")
        subject_renderer.assert_(release="0.0.0")
        body_renderer.assert_(project="test_project")
        body_renderer.assert_(release="0.0.0")
        body_renderer.assert_(release_date=release.created.strftime("%Y-%m-%d"))
        body_renderer.assert_(submitter=stub_submitter_user.username)
        body_renderer.assert_(submitter_role="owner")
        body_renderer.assert_(recipient_role_descr="an owner")

        assert pyramid_request.task.calls == [
            pretend.call(send_email),
            pretend.call(send_email),
        ]

        assert send_email.delay.calls == [
            pretend.call(
                "username <email@example.com>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "email@example.com",
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
            pretend.call(
                "submitterusername <submiteremail@example.com>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_submitter_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "submiteremail@example.com",
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            ),
        ]


class TestRemovedReleaseEmail:
    def test_send_removed_project_release_email_to_maintainer(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        stub_user = pretend.stub(
            id="id_1",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        stub_submitter_user = pretend.stub(
            id="id_2",
            username="submitterusername",
            name="",
            email="submiteremail@example.com",
            primary_email=pretend.stub(
                email="submiteremail@example.com", verified=True
            ),
        )

        subject_renderer = pyramid_config.testing_add_renderer(
            "email/removed-project-release/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/removed-project-release/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/removed-project-release/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        ids = [stub_submitter_user.id, stub_user.id]
        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=ids.pop())
                )
            ),
        )
        pyramid_request.user = stub_submitter_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        release = pretend.stub(
            version="0.0.0",
            project=pretend.stub(name="test_project"),
            created=datetime.datetime(2017, 2, 5, 0, 0, 0, 0),
            yanked_reason="",
        )

        result = email.send_removed_project_release_email(
            pyramid_request,
            [stub_user, stub_submitter_user],
            release=release,
            submitter_name=stub_submitter_user.username,
            submitter_role="Owner",
            recipient_role="Maintainer",
        )

        assert result == {
            "project_name": release.project.name,
            "release_version": release.version,
            "release_date": release.created.strftime("%Y-%m-%d"),
            "submitter_name": stub_submitter_user.username,
            "submitter_role": "owner",
            "recipient_role_descr": "a maintainer",
        }

        subject_renderer.assert_(project_name="test_project")
        subject_renderer.assert_(release_version="0.0.0")
        body_renderer.assert_(project_name="test_project")
        body_renderer.assert_(release_version="0.0.0")
        body_renderer.assert_(release_date=release.created.strftime("%Y-%m-%d"))
        body_renderer.assert_(submitter_name=stub_submitter_user.username)
        body_renderer.assert_(submitter_role="owner")
        body_renderer.assert_(recipient_role_descr="a maintainer")

        assert pyramid_request.task.calls == [
            pretend.call(send_email),
            pretend.call(send_email),
        ]

        assert send_email.delay.calls == [
            pretend.call(
                "username <email@example.com>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "email@example.com",
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
            pretend.call(
                "submitterusername <submiteremail@example.com>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_submitter_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "submiteremail@example.com",
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            ),
        ]

    def test_send_removed_project_release_email_to_owner(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        stub_user = pretend.stub(
            id="id_1",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        stub_submitter_user = pretend.stub(
            id="id_2",
            username="submitterusername",
            name="",
            email="submiteremail@example.com",
            primary_email=pretend.stub(
                email="submiteremail@example.com", verified=True
            ),
        )

        subject_renderer = pyramid_config.testing_add_renderer(
            "email/removed-project-release/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/removed-project-release/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/removed-project-release/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        ids = [stub_submitter_user.id, stub_user.id]
        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=ids.pop())
                )
            ),
        )
        pyramid_request.user = stub_submitter_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        release = pretend.stub(
            version="0.0.0",
            project=pretend.stub(name="test_project"),
            created=datetime.datetime(2017, 2, 5, 0, 0, 0, 0),
            yanked_reason="",
        )

        result = email.send_removed_project_release_email(
            pyramid_request,
            [stub_user, stub_submitter_user],
            release=release,
            submitter_name=stub_submitter_user.username,
            submitter_role="Owner",
            recipient_role="Owner",
        )

        assert result == {
            "project_name": release.project.name,
            "release_version": release.version,
            "release_date": release.created.strftime("%Y-%m-%d"),
            "submitter_name": stub_submitter_user.username,
            "submitter_role": "owner",
            "recipient_role_descr": "an owner",
        }

        subject_renderer.assert_(project_name="test_project")
        subject_renderer.assert_(release_version="0.0.0")
        body_renderer.assert_(project_name="test_project")
        body_renderer.assert_(release_version="0.0.0")
        body_renderer.assert_(release_date=release.created.strftime("%Y-%m-%d"))
        body_renderer.assert_(submitter_name=stub_submitter_user.username)
        body_renderer.assert_(submitter_role="owner")
        body_renderer.assert_(recipient_role_descr="an owner")

        assert pyramid_request.task.calls == [
            pretend.call(send_email),
            pretend.call(send_email),
        ]

        assert send_email.delay.calls == [
            pretend.call(
                "username <email@example.com>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "email@example.com",
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
            pretend.call(
                "submitterusername <submiteremail@example.com>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_submitter_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "submiteremail@example.com",
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            ),
        ]


class TestRemovedReleaseFileEmail:
    def test_send_removed_project_release_file_email_to_owner(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        stub_user = pretend.stub(
            id="id_1",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        stub_submitter_user = pretend.stub(
            id="id_2",
            username="submitterusername",
            name="",
            email="submiteremail@example.com",
            primary_email=pretend.stub(
                email="submiteremail@example.com", verified=True
            ),
        )

        subject_renderer = pyramid_config.testing_add_renderer(
            "email/removed-project-release-file/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/removed-project-release-file/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/removed-project-release-file/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        ids = [stub_submitter_user.id, stub_user.id]
        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=ids.pop())
                )
            ),
        )
        pyramid_request.user = stub_submitter_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        release = pretend.stub(
            version="0.0.0",
            project=pretend.stub(name="test_project"),
            created=datetime.datetime(2017, 2, 5, 0, 0, 0, 0),
            yanked_reason="",
        )

        result = email.send_removed_project_release_file_email(
            pyramid_request,
            [stub_user, stub_submitter_user],
            file="test-file-0.0.0.tar.gz",
            release=release,
            submitter_name=stub_submitter_user.username,
            submitter_role="Owner",
            recipient_role="Owner",
        )

        assert result == {
            "file": "test-file-0.0.0.tar.gz",
            "project_name": release.project.name,
            "release_version": release.version,
            "submitter_name": stub_submitter_user.username,
            "submitter_role": "owner",
            "recipient_role_descr": "an owner",
        }

        subject_renderer.assert_(project_name="test_project")
        subject_renderer.assert_(release_version="0.0.0")
        body_renderer.assert_(file="test-file-0.0.0.tar.gz")
        body_renderer.assert_(release_version="0.0.0")
        body_renderer.assert_(project_name="test_project")
        body_renderer.assert_(submitter_name=stub_submitter_user.username)
        body_renderer.assert_(submitter_role="owner")
        body_renderer.assert_(recipient_role_descr="an owner")

        assert pyramid_request.task.calls == [
            pretend.call(send_email),
            pretend.call(send_email),
        ]

        assert send_email.delay.calls == [
            pretend.call(
                "username <email@example.com>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "email@example.com",
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
            pretend.call(
                "submitterusername <submiteremail@example.com>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_submitter_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "submiteremail@example.com",
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            ),
        ]

    def test_send_removed_project_release_file_email_to_maintainer(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        stub_user = pretend.stub(
            id="id_1",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        stub_submitter_user = pretend.stub(
            id="id_2",
            username="submitterusername",
            name="",
            email="submiteremail@example.com",
            primary_email=pretend.stub(
                email="submiteremail@example.com", verified=True
            ),
        )

        subject_renderer = pyramid_config.testing_add_renderer(
            "email/removed-project-release-file/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/removed-project-release-file/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            "email/removed-project-release-file/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        ids = [stub_submitter_user.id, stub_user.id]
        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=ids.pop())
                )
            ),
        )
        pyramid_request.user = stub_submitter_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        release = pretend.stub(
            version="0.0.0",
            project=pretend.stub(name="test_project"),
            created=datetime.datetime(2017, 2, 5, 0, 0, 0, 0),
            yanked_reason="",
        )

        result = email.send_removed_project_release_file_email(
            pyramid_request,
            [stub_user, stub_submitter_user],
            file="test-file-0.0.0.tar.gz",
            release=release,
            submitter_name=stub_submitter_user.username,
            submitter_role="Owner",
            recipient_role="Maintainer",
        )

        assert result == {
            "file": "test-file-0.0.0.tar.gz",
            "project_name": release.project.name,
            "release_version": release.version,
            "submitter_name": stub_submitter_user.username,
            "submitter_role": "owner",
            "recipient_role_descr": "a maintainer",
        }

        subject_renderer.assert_(project_name="test_project")
        subject_renderer.assert_(release_version="0.0.0")
        body_renderer.assert_(file="test-file-0.0.0.tar.gz")
        body_renderer.assert_(release_version="0.0.0")
        body_renderer.assert_(project_name="test_project")
        body_renderer.assert_(submitter_name=stub_submitter_user.username)
        body_renderer.assert_(submitter_role="owner")
        body_renderer.assert_(recipient_role_descr="a maintainer")

        assert pyramid_request.task.calls == [
            pretend.call(send_email),
            pretend.call(send_email),
        ]

        assert send_email.delay.calls == [
            pretend.call(
                "username <email@example.com>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "email@example.com",
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
            pretend.call(
                "submitterusername <submiteremail@example.com>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_submitter_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "submiteremail@example.com",
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            ),
        ]


class TestTwoFactorEmail:
    @pytest.mark.parametrize(
        ("action", "method", "pretty_method"),
        [
            ("added", "totp", "TOTP"),
            ("removed", "totp", "TOTP"),
            ("added", "webauthn", "WebAuthn"),
            ("removed", "webauthn", "WebAuthn"),
        ],
    )
    def test_two_factor_email(
        self,
        pyramid_request,
        pyramid_config,
        monkeypatch,
        action,
        method,
        pretty_method,
    ):
        stub_user = pretend.stub(
            id="id",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        subject_renderer = pyramid_config.testing_add_renderer(
            f"email/two-factor-{action}/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            f"email/two-factor-{action}/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            f"email/two-factor-{action}/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=stub_user.id)
                )
            ),
        )
        pyramid_request.user = stub_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        send_method = getattr(email, f"send_two_factor_{action}_email")
        result = send_method(pyramid_request, stub_user, method=method)

        assert result == {"method": pretty_method, "username": stub_user.username}
        subject_renderer.assert_()
        body_renderer.assert_(method=pretty_method, username=stub_user.username)
        html_renderer.assert_(method=pretty_method, username=stub_user.username)
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{stub_user.username} <{stub_user.email}>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": stub_user.email,
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            )
        ]


class TestRecoveryCodeEmails:
    @pytest.mark.parametrize(
        "fn, template_name",
        [
            (email.send_recovery_codes_generated_email, "recovery-codes-generated"),
            (email.send_recovery_code_used_email, "recovery-code-used"),
            (email.send_recovery_code_reminder_email, "recovery-code-reminder"),
        ],
    )
    def test_recovery_code_emails(
        self, pyramid_request, pyramid_config, monkeypatch, fn, template_name
    ):
        stub_user = pretend.stub(
            id="id",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        subject_renderer = pyramid_config.testing_add_renderer(
            f"email/{template_name}/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            f"email/{template_name}/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            f"email/{template_name}/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=stub_user.id)
                )
            ),
        )
        pyramid_request.user = stub_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        result = fn(pyramid_request, stub_user)

        assert result == {"username": stub_user.username}
        subject_renderer.assert_()
        body_renderer.assert_(username=stub_user.username)
        html_renderer.assert_(username=stub_user.username)
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{stub_user.username} <{stub_user.email}>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": stub_user.email,
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            )
        ]


class TestTrustedPublisherEmails:
    @pytest.mark.parametrize(
        "fn, template_name",
        [
            (
                email.send_pending_trusted_publisher_invalidated_email,
                "pending-trusted-publisher-invalidated",
            ),
        ],
    )
    def test_pending_trusted_publisher_emails(
        self, pyramid_request, pyramid_config, monkeypatch, fn, template_name
    ):
        stub_user = pretend.stub(
            id="id",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        subject_renderer = pyramid_config.testing_add_renderer(
            f"email/{template_name}/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            f"email/{template_name}/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            f"email/{template_name}/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=stub_user.id)
                )
            ),
        )
        pyramid_request.user = stub_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        project_name = "test_project"
        result = fn(
            pyramid_request,
            stub_user,
            project_name=project_name,
        )

        assert result == {
            "project_name": project_name,
        }
        subject_renderer.assert_()
        body_renderer.assert_(project_name=project_name)
        html_renderer.assert_(project_name=project_name)
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{stub_user.username} <{stub_user.email}>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": stub_user.email,
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            )
        ]

    @pytest.mark.parametrize(
        "fn, template_name",
        [
            (email.send_trusted_publisher_added_email, "trusted-publisher-added"),
            (email.send_trusted_publisher_removed_email, "trusted-publisher-removed"),
        ],
    )
    def test_trusted_publisher_emails(
        self, pyramid_request, pyramid_config, monkeypatch, fn, template_name
    ):
        stub_user = pretend.stub(
            id="id",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        subject_renderer = pyramid_config.testing_add_renderer(
            f"email/{template_name}/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            f"email/{template_name}/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            f"email/{template_name}/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=stub_user.id)
                )
            ),
        )
        pyramid_request.user = stub_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        project_name = "test_project"
        fakepublisher = pretend.stub(
            publisher_name="fakepublisher",
            repository_owner="fakeowner",
            repository_name="fakerepository",
            environment="fakeenvironment",
        )
        # NOTE: Can't set __str__ using pretend.stub()
        monkeypatch.setattr(
            fakepublisher.__class__, "__str__", lambda s: "fakespecifier"
        )

        result = fn(
            pyramid_request,
            stub_user,
            project_name=project_name,
            publisher=fakepublisher,
        )

        assert result == {
            "username": stub_user.username,
            "project_name": project_name,
            "publisher": fakepublisher,
        }
        subject_renderer.assert_()
        body_renderer.assert_(username=stub_user.username, project_name=project_name)
        html_renderer.assert_(username=stub_user.username, project_name=project_name)
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{stub_user.username} <{stub_user.email}>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": stub_user.email,
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            )
        ]

    def test_api_token_warning_with_trusted_publisher_emails(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        template_name = "api-token-used-in-trusted-publisher-project"
        # We set up two users to receive the email. The owner of the API token
        # will be stub_user, their username should be the one mentioned in the
        # email body.
        stub_user = pretend.stub(
            id="id",
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        stub_user_maintainer = pretend.stub(
            id="id_maintainer",
            username="username_maintainer",
            name="",
            email="email_maintainer@example.com",
            primary_email=pretend.stub(
                email="email_maintainer@example.com", verified=True
            ),
        )
        subject_renderer = pyramid_config.testing_add_renderer(
            f"email/{template_name}/subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            f"email/{template_name}/body.txt"
        )
        body_renderer.string_response = "Email Body"
        html_renderer = pyramid_config.testing_add_renderer(
            f"email/{template_name}/body.html"
        )
        html_renderer.string_response = "Email HTML Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        pyramid_request.db = pretend.stub(
            query=lambda a: pretend.stub(
                filter=lambda *a: pretend.stub(
                    one=lambda: pretend.stub(user_id=stub_user.id)
                )
            ),
        )
        pyramid_request.user = stub_user
        pyramid_request.registry.settings = {"mail.sender": "noreply@example.com"}

        project_name = "test_project"
        api_token_name = "old_api_token"
        result = email.send_api_token_used_in_trusted_publisher_project_email(
            pyramid_request,
            [stub_user, stub_user_maintainer],
            project_name=project_name,
            token_owner_username=stub_user.username,
            token_name=api_token_name,
        )

        assert result == {
            "project_name": project_name,
            "token_owner_username": stub_user.username,
            "token_name": api_token_name,
        }
        subject_renderer.assert_()
        body_renderer.assert_(
            project_name=project_name,
            token_owner_username=stub_user.username,
            token_name=api_token_name,
        )
        html_renderer.assert_(
            project_name=project_name,
            token_owner_username=stub_user.username,
            token_name=api_token_name,
        )
        assert pyramid_request.task.calls == [
            pretend.call(send_email),
            pretend.call(send_email),
        ]
        assert send_email.delay.calls == [
            pretend.call(
                f"{stub_user.username} <{stub_user.email}>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": stub_user.email,
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            ),
            pretend.call(
                f"{stub_user_maintainer.username} <{stub_user_maintainer.email}>",
                {
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": stub_user_maintainer.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": stub_user_maintainer.email,
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            ),
        ]
