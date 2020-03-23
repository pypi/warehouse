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

import attr
import celery.exceptions
import pretend
import pytest

from warehouse import email
from warehouse.accounts.interfaces import ITokenService
from warehouse.email.interfaces import IEmailSender
from warehouse.email.services import EmailMessage


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
        self, name, username, primary_email, address, expected
    ):
        task = pretend.stub(delay=pretend.call_recorder(lambda *a, **kw: None))
        request = pretend.stub(task=pretend.call_recorder(lambda x: task))

        user = pretend.stub(
            name=name,
            username=username,
            primary_email=pretend.stub(email=primary_email, verified=True),
        )

        if address is not None:
            address = pretend.stub(email=address, verified=True)

        msg = EmailMessage(subject="My Subject", body_text="My Body")

        email._send_email_to_user(request, user, msg, email=address)

        assert request.task.calls == [pretend.call(email.send_email)]
        assert task.delay.calls == [
            pretend.call(
                expected,
                {"subject": "My Subject", "body_text": "My Body", "body_html": None},
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
            )
        )

        if address is not None:
            address = pretend.stub(email=address, verified=False)

        msg = EmailMessage(subject="My Subject", body_text="My Body")

        email._send_email_to_user(request, user, msg, email=address)

        assert request.task.calls == []
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
        self, username, primary_email, address, expected
    ):
        task = pretend.stub(delay=pretend.call_recorder(lambda *a, **kw: None))
        request = pretend.stub(task=pretend.call_recorder(lambda x: task))

        user = pretend.stub(
            username=username,
            name="",
            primary_email=pretend.stub(
                email=primary_email, verified=True if address is not None else False
            ),
        )

        if address is not None:
            address = pretend.stub(email=address, verified=False)

        msg = EmailMessage(subject="My Subject", body_text="My Body")

        email._send_email_to_user(
            request, user, msg, email=address, allow_unverified=True
        )

        assert request.task.calls == [pretend.call(email.send_email)]
        assert task.delay.calls == [
            pretend.call(
                expected,
                {"subject": "My Subject", "body_text": "My Body", "body_html": None},
            )
        ]


class TestSendEmail:
    def test_send_email_success(self, monkeypatch):
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

        sender = FakeMailSender()
        task = pretend.stub()
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda *a, **kw: sender)
        )

        msg = EmailMessage(subject="subject", body_text="body")

        email.send_email(task, request, "recipient", attr.asdict(msg))

        assert request.find_service.calls == [pretend.call(IEmailSender)]
        assert sender.emails == [
            {
                "subject": "subject",
                "body": "body",
                "html": None,
                "recipient": "recipient",
            }
        ]

    def test_send_email_failure(self, monkeypatch):
        exc = Exception()

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
        msg = EmailMessage(subject="subject", body_text="body")

        with pytest.raises(celery.exceptions.Retry):
            email.send_email(task, request, "recipient", attr.asdict(msg))

        assert task.retry.calls == [pretend.call(exc=exc)]


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
        pyramid_request.find_service = pretend.call_recorder(
            lambda *a, **kw: token_service
        )

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
        assert pyramid_request.find_service.calls == [
            pretend.call(ITokenService, name="password")
        ]
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                "name_value <"
                + (stub_user.email if email_addr is None else email_addr)
                + ">",
                attr.asdict(
                    EmailMessage(
                        subject="Email Subject",
                        body_text="Email Body",
                        body_html=(
                            "<html>\n<head></head>\n"
                            "<body><p>Email HTML Body</p></body>\n</html>\n"
                        ),
                    )
                ),
            )
        ]


class TestEmailVerificationEmail:
    def test_email_verification_email(
        self, pyramid_request, pyramid_config, token_service, monkeypatch
    ):

        stub_email = pretend.stub(id="id", email="email@example.com", verified=False)
        pyramid_request.method = "POST"
        token_service.dumps = pretend.call_recorder(lambda a: "TOKEN")
        pyramid_request.find_service = pretend.call_recorder(
            lambda *a, **kw: token_service
        )

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

        result = email.send_email_verification_email(
            pyramid_request,
            (
                pretend.stub(username=None, name=None, email="foo@example.com"),
                stub_email,
            ),
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
        assert pyramid_request.find_service.calls == [
            pretend.call(ITokenService, name="email")
        ]
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                stub_email.email,
                attr.asdict(
                    EmailMessage(
                        subject="Email Subject",
                        body_text="Email Body",
                        body_html=(
                            "<html>\n<head></head>\n"
                            "<body><p>Email HTML Body</p></body>\n</html>\n"
                        ),
                    )
                ),
            )
        ]


class TestPasswordChangeEmail:
    def test_password_change_email(self, pyramid_request, pyramid_config, monkeypatch):
        stub_user = pretend.stub(
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

        result = email.send_password_change_email(pyramid_request, stub_user)

        assert result == {"username": stub_user.username}
        subject_renderer.assert_()
        body_renderer.assert_(username=stub_user.username)
        html_renderer.assert_(username=stub_user.username)
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{stub_user.username} <{stub_user.email}>",
                attr.asdict(
                    EmailMessage(
                        subject="Email Subject",
                        body_text="Email Body",
                        body_html=(
                            "<html>\n<head></head>\n"
                            "<body><p>Email HTML Body</p></body>\n</html>\n"
                        ),
                    )
                ),
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

        result = email.send_password_compromised_email_hibp(pyramid_request, stub_user)

        assert result == {}
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{stub_user.username} <{stub_user.email}>",
                attr.asdict(
                    EmailMessage(
                        subject="Email Subject",
                        body_text="Email Body",
                        body_html=(
                            "<html>\n<head></head>\n"
                            "<body><p>Email HTML Body</p></body>\n</html>\n"
                        ),
                    )
                ),
            )
        ]


class TestPasswordCompromisedEmail:
    @pytest.mark.parametrize("verified", [True, False])
    def test_password_compromised_email(
        self, pyramid_request, pyramid_config, monkeypatch, verified
    ):
        stub_user = pretend.stub(
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

        result = email.send_password_compromised_email(pyramid_request, stub_user)

        assert result == {}
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{stub_user.username} <{stub_user.email}>",
                attr.asdict(
                    EmailMessage(
                        subject="Email Subject",
                        body_text="Email Body",
                        body_html=(
                            "<html>\n<head></head>\n"
                            "<body><p>Email HTML Body</p></body>\n</html>\n"
                        ),
                    )
                ),
            )
        ]


class TestAccountDeletionEmail:
    def test_account_deletion_email(self, pyramid_request, pyramid_config, monkeypatch):

        stub_user = pretend.stub(
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

        result = email.send_account_deletion_email(pyramid_request, stub_user)

        assert result == {"username": stub_user.username}
        subject_renderer.assert_()
        body_renderer.assert_(username=stub_user.username)
        html_renderer.assert_(username=stub_user.username)
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                f"{stub_user.username} <{stub_user.email}>",
                attr.asdict(
                    EmailMessage(
                        subject="Email Subject",
                        body_text="Email Body",
                        body_html=(
                            "<html>\n<head></head>\n"
                            "<body><p>Email HTML Body</p></body>\n</html>\n"
                        ),
                    )
                ),
            )
        ]

    def test_account_deletion_email_unverified(
        self, pyramid_request, pyramid_config, monkeypatch
    ):

        stub_user = pretend.stub(
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
            email="new_email@example.com", username="username", name=""
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
                attr.asdict(
                    EmailMessage(
                        subject="Email Subject",
                        body_text="Email Body",
                        body_html=(
                            "<html>\n<head></head>\n"
                            "<body><p>Email HTML Body</p></body>\n</html>\n"
                        ),
                    )
                ),
            )
        ]

    def test_primary_email_change_email_unverified(
        self, pyramid_request, pyramid_config, monkeypatch
    ):

        stub_user = pretend.stub(
            email="new_email@example.com", username="username", name=""
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


class TestCollaboratorAddedEmail:
    def test_collaborator_added_email(
        self, pyramid_request, pyramid_config, monkeypatch
    ):

        stub_user = pretend.stub(
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        stub_submitter_user = pretend.stub(
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
                attr.asdict(
                    EmailMessage(
                        subject="Email Subject",
                        body_text="Email Body",
                        body_html=(
                            "<html>\n<head></head>\n"
                            "<body><p>Email HTML Body</p></body>\n</html>\n"
                        ),
                    )
                ),
            ),
            pretend.call(
                "submitterusername <submiteremail@example.com>",
                attr.asdict(
                    EmailMessage(
                        subject="Email Subject",
                        body_text="Email Body",
                        body_html=(
                            "<html>\n<head></head>\n"
                            "<body><p>Email HTML Body</p></body>\n</html>\n"
                        ),
                    )
                ),
            ),
        ]

    def test_collaborator_added_email_unverified(
        self, pyramid_request, pyramid_config, monkeypatch
    ):

        stub_user = pretend.stub(
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=False),
        )
        stub_submitter_user = pretend.stub(
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
                attr.asdict(
                    EmailMessage(
                        subject="Email Subject",
                        body_text="Email Body",
                        body_html=(
                            "<html>\n<head></head>\n"
                            "<body><p>Email HTML Body</p></body>\n</html>\n"
                        ),
                    )
                ),
            )
        ]


class TestAddedAsCollaboratorEmail:
    def test_added_as_collaborator_email(
        self, pyramid_request, pyramid_config, monkeypatch
    ):

        stub_user = pretend.stub(
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        stub_submitter_user = pretend.stub(
            username="submitterusername", email="submiteremail"
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

        result = email.send_added_as_collaborator_email(
            pyramid_request,
            stub_user,
            submitter=stub_submitter_user,
            project_name="test_project",
            role="Owner",
        )

        assert result == {
            "project": "test_project",
            "role": "Owner",
            "submitter": stub_submitter_user.username,
        }
        subject_renderer.assert_()
        body_renderer.assert_(submitter=stub_submitter_user.username)
        body_renderer.assert_(project="test_project")
        body_renderer.assert_(role="Owner")
        html_renderer.assert_(submitter=stub_submitter_user.username)
        html_renderer.assert_(project="test_project")
        html_renderer.assert_(role="Owner")

        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                "username <email@example.com>",
                attr.asdict(
                    EmailMessage(
                        subject="Email Subject",
                        body_text="Email Body",
                        body_html=(
                            "<html>\n<head></head>\n"
                            "<body><p>Email HTML Body</p></body>\n</html>\n"
                        ),
                    )
                ),
            )
        ]

    def test_added_as_collaborator_email_unverified(
        self, pyramid_request, pyramid_config, monkeypatch
    ):

        stub_user = pretend.stub(
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=False),
        )
        stub_submitter_user = pretend.stub(
            username="submitterusername", email="submiteremail"
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

        result = email.send_added_as_collaborator_email(
            pyramid_request,
            stub_user,
            submitter=stub_submitter_user,
            project_name="test_project",
            role="Owner",
        )

        assert result == {
            "project": "test_project",
            "role": "Owner",
            "submitter": stub_submitter_user.username,
        }
        subject_renderer.assert_()
        body_renderer.assert_(submitter=stub_submitter_user.username)
        body_renderer.assert_(project="test_project")
        body_renderer.assert_(role="Owner")
        html_renderer.assert_(submitter=stub_submitter_user.username)
        html_renderer.assert_(project="test_project")
        html_renderer.assert_(role="Owner")

        assert pyramid_request.task.calls == []
        assert send_email.delay.calls == []


class TestRemovedPackageEmail:
    def test_removed_project_email_to_maintainer(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        stub_user = pretend.stub(
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        stub_submitter_user = pretend.stub(
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

        result = email.send_removed_project_email(
            pyramid_request,
            [stub_user, stub_submitter_user],
            project_name="test_project",
            submitter_name=stub_submitter_user.username,
            submitter_role="Owner",
            recipient_role="Maintainer",
        )

        assert result == {
            "project": "test_project",
            "submitter": stub_submitter_user.username,
            "submitter_role": "owner",
            "recipient_role_descr": "a maintainer",
        }

        subject_renderer.assert_(project="test_project")
        body_renderer.assert_(project="test_project")
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
                attr.asdict(
                    EmailMessage(
                        subject="Email Subject",
                        body_text="Email Body",
                        body_html=(
                            "<html>\n<head></head>\n"
                            "<body><p>Email HTML Body</p></body>\n</html>\n"
                        ),
                    ),
                ),
            ),
            pretend.call(
                "submitterusername <submiteremail@example.com>",
                attr.asdict(
                    EmailMessage(
                        subject="Email Subject",
                        body_text="Email Body",
                        body_html=(
                            "<html>\n<head></head>\n"
                            "<body><p>Email HTML Body</p></body>\n</html>\n"
                        ),
                    )
                ),
            ),
        ]

    def test_removed_project_email_to_owner(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        stub_user = pretend.stub(
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        stub_submitter_user = pretend.stub(
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

        result = email.send_removed_project_email(
            pyramid_request,
            [stub_user, stub_submitter_user],
            project_name="test_project",
            submitter_name=stub_submitter_user.username,
            submitter_role="Owner",
            recipient_role="Owner",
        )

        assert result == {
            "project": "test_project",
            "submitter": stub_submitter_user.username,
            "submitter_role": "owner",
            "recipient_role_descr": "an owner",
        }

        subject_renderer.assert_(project="test_project")
        body_renderer.assert_(project="test_project")
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
                attr.asdict(
                    EmailMessage(
                        subject="Email Subject",
                        body_text="Email Body",
                        body_html=(
                            "<html>\n<head></head>\n"
                            "<body><p>Email HTML Body</p></body>\n</html>\n"
                        ),
                    ),
                ),
            ),
            pretend.call(
                "submitterusername <submiteremail@example.com>",
                attr.asdict(
                    EmailMessage(
                        subject="Email Subject",
                        body_text="Email Body",
                        body_html=(
                            "<html>\n<head></head>\n"
                            "<body><p>Email HTML Body</p></body>\n</html>\n"
                        ),
                    )
                ),
            ),
        ]


class TestRemovedReleaseEmail:
    def test_send_removed_project_release_email_to_maintainer(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        stub_user = pretend.stub(
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        stub_submitter_user = pretend.stub(
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

        release = pretend.stub(
            version="0.0.0",
            project=pretend.stub(name="test_project"),
            created=datetime.datetime(2017, 2, 5, 0, 0, 0, 0),
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
                attr.asdict(
                    EmailMessage(
                        subject="Email Subject",
                        body_text="Email Body",
                        body_html=(
                            "<html>\n<head></head>\n"
                            "<body><p>Email HTML Body</p></body>\n</html>\n"
                        ),
                    ),
                ),
            ),
            pretend.call(
                "submitterusername <submiteremail@example.com>",
                attr.asdict(
                    EmailMessage(
                        subject="Email Subject",
                        body_text="Email Body",
                        body_html=(
                            "<html>\n<head></head>\n"
                            "<body><p>Email HTML Body</p></body>\n</html>\n"
                        ),
                    )
                ),
            ),
        ]

    def test_send_removed_project_release_emai_to_owner(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        stub_user = pretend.stub(
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        stub_submitter_user = pretend.stub(
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

        release = pretend.stub(
            version="0.0.0",
            project=pretend.stub(name="test_project"),
            created=datetime.datetime(2017, 2, 5, 0, 0, 0, 0),
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
                attr.asdict(
                    EmailMessage(
                        subject="Email Subject",
                        body_text="Email Body",
                        body_html=(
                            "<html>\n<head></head>\n"
                            "<body><p>Email HTML Body</p></body>\n</html>\n"
                        ),
                    ),
                ),
            ),
            pretend.call(
                "submitterusername <submiteremail@example.com>",
                attr.asdict(
                    EmailMessage(
                        subject="Email Subject",
                        body_text="Email Body",
                        body_html=(
                            "<html>\n<head></head>\n"
                            "<body><p>Email HTML Body</p></body>\n</html>\n"
                        ),
                    )
                ),
            ),
        ]


class TestRemovedReleaseFileEmail:
    def test_send_removed_project_release_file_email_to_owner(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        stub_user = pretend.stub(
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        stub_submitter_user = pretend.stub(
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

        release = pretend.stub(
            version="0.0.0",
            project=pretend.stub(name="test_project"),
            created=datetime.datetime(2017, 2, 5, 0, 0, 0, 0),
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
                attr.asdict(
                    EmailMessage(
                        subject="Email Subject",
                        body_text="Email Body",
                        body_html=(
                            "<html>\n<head></head>\n"
                            "<body><p>Email HTML Body</p></body>\n</html>\n"
                        ),
                    ),
                ),
            ),
            pretend.call(
                "submitterusername <submiteremail@example.com>",
                attr.asdict(
                    EmailMessage(
                        subject="Email Subject",
                        body_text="Email Body",
                        body_html=(
                            "<html>\n<head></head>\n"
                            "<body><p>Email HTML Body</p></body>\n</html>\n"
                        ),
                    )
                ),
            ),
        ]

    def test_send_removed_project_release_file_email_to_maintainer(
        self, pyramid_request, pyramid_config, monkeypatch
    ):
        stub_user = pretend.stub(
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        stub_submitter_user = pretend.stub(
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

        release = pretend.stub(
            version="0.0.0",
            project=pretend.stub(name="test_project"),
            created=datetime.datetime(2017, 2, 5, 0, 0, 0, 0),
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
                attr.asdict(
                    EmailMessage(
                        subject="Email Subject",
                        body_text="Email Body",
                        body_html=(
                            "<html>\n<head></head>\n"
                            "<body><p>Email HTML Body</p></body>\n</html>\n"
                        ),
                    ),
                ),
            ),
            pretend.call(
                "submitterusername <submiteremail@example.com>",
                attr.asdict(
                    EmailMessage(
                        subject="Email Subject",
                        body_text="Email Body",
                        body_html=(
                            "<html>\n<head></head>\n"
                            "<body><p>Email HTML Body</p></body>\n</html>\n"
                        ),
                    )
                ),
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
                attr.asdict(
                    EmailMessage(
                        subject="Email Subject",
                        body_text="Email Body",
                        body_html=(
                            "<html>\n<head></head>\n"
                            "<body><p>Email HTML Body</p></body>\n</html>\n"
                        ),
                    )
                ),
            )
        ]
