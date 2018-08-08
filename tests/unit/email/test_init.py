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

import celery.exceptions
import pretend
import pytest

from warehouse import email
from warehouse.accounts.interfaces import ITokenService
from warehouse.email.interfaces import IEmailSender


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

        subject = "My Subject"
        body = "My Body"

        email._send_email_to_user(request, user, subject, body, email=address)

        assert request.task.calls == [pretend.call(email.send_email)]
        assert task.delay.calls == [pretend.call(subject, body, recipient=expected)]

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

        subject = "My Subject"
        body = "My Body"

        email._send_email_to_user(request, user, subject, body, email=address)

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

        subject = "My Subject"
        body = "My Body"

        email._send_email_to_user(
            request, user, subject, body, email=address, allow_unverified=True
        )

        assert request.task.calls == [pretend.call(email.send_email)]
        assert task.delay.calls == [pretend.call(subject, body, recipient=expected)]


class TestSendEmail:
    def test_send_email_success(self, monkeypatch):
        class FakeMailSender:
            def __init__(self):
                self.emails = []

            def send(self, subject, body, *, recipient):
                self.emails.append(
                    {"subject": subject, "body": body, "recipient": recipient}
                )

        sender = FakeMailSender()
        task = pretend.stub()
        request = pretend.stub(
            find_service=pretend.call_recorder(lambda *a, **kw: sender),
            registry=pretend.stub(settings={"site.name": "DevPyPI"}),
        )

        email.send_email(task, request, "subject", "body", recipient="recipient")

        assert request.find_service.calls == [pretend.call(IEmailSender)]
        assert sender.emails == [
            {"subject": "[DevPyPI] subject", "body": "body", "recipient": "recipient"}
        ]

    def test_send_email_failure(self, monkeypatch):
        exc = Exception()

        class FakeMailSender:
            def send(self, subject, body, *, recipient):
                raise exc

        class Task:
            @staticmethod
            @pretend.call_recorder
            def retry(exc):
                raise celery.exceptions.Retry

        sender, task = FakeMailSender(), Task()
        request = pretend.stub(
            find_service=lambda *a, **kw: sender,
            registry=pretend.stub(settings={"site.name": "DevPyPI"}),
        )

        with pytest.raises(celery.exceptions.Retry):
            email.send_email(task, request, "subject", "body", recipient="recipient")

        assert task.retry.calls == [pretend.call(exc=exc)]


class TestSendPasswordResetEmail:
    @pytest.mark.parametrize("verified", [True, False])
    def test_send_password_reset_email(
        self, verified, pyramid_request, pyramid_config, token_service, monkeypatch
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
        pyramid_request.method = "POST"
        token_service.dumps = pretend.call_recorder(lambda a: "TOKEN")
        pyramid_request.find_service = pretend.call_recorder(
            lambda *a, **kw: token_service
        )

        subject_renderer = pyramid_config.testing_add_renderer(
            "email/password-reset.subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/password-reset.body.txt"
        )
        body_renderer.string_response = "Email Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        result = email.send_password_reset_email(pyramid_request, user=stub_user)

        assert result == {
            "token": "TOKEN",
            "username": stub_user.username,
            "n_hours": token_service.max_age // 60 // 60,
        }
        subject_renderer.assert_()
        body_renderer.assert_(token="TOKEN", username=stub_user.username)
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
                "Email Subject",
                "Email Body",
                recipient="name_value <" + stub_user.email + ">",
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
            "email/verify-email.subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/verify-email.body.txt"
        )
        body_renderer.string_response = "Email Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        result = email.send_email_verification_email(
            pyramid_request,
            pretend.stub(username=None, name=None, email="foo@example.com"),
            email=stub_email,
        )

        assert result == {
            "token": "TOKEN",
            "email_address": stub_email.email,
            "n_hours": token_service.max_age // 60 // 60,
        }
        subject_renderer.assert_()
        body_renderer.assert_(token="TOKEN", email_address=stub_email.email)
        assert token_service.dumps.calls == [
            pretend.call({"action": "email-verify", "email.id": str(stub_email.id)})
        ]
        assert pyramid_request.find_service.calls == [
            pretend.call(ITokenService, name="email")
        ]
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call("Email Subject", "Email Body", recipient=stub_email.email)
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
            "email/password-change.subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/password-change.body.txt"
        )
        body_renderer.string_response = "Email Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        result = email.send_password_change_email(pyramid_request, user=stub_user)

        assert result == {"username": stub_user.username}
        subject_renderer.assert_()
        body_renderer.assert_(username=stub_user.username)
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                "Email Subject",
                "Email Body",
                recipient=f"{stub_user.username} <{stub_user.email}>",
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
            "email/password-change.subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/password-change.body.txt"
        )
        body_renderer.string_response = "Email Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        result = email.send_password_change_email(pyramid_request, user=stub_user)

        assert result == {"username": stub_user.username}
        subject_renderer.assert_()
        body_renderer.assert_(username=stub_user.username)
        assert pyramid_request.task.calls == []
        assert send_email.delay.calls == []


class TestAccountDeletionEmail:
    def test_account_deletion_email(self, pyramid_request, pyramid_config, monkeypatch):

        stub_user = pretend.stub(
            username="username",
            name="",
            email="email@example.com",
            primary_email=pretend.stub(email="email@example.com", verified=True),
        )
        subject_renderer = pyramid_config.testing_add_renderer(
            "email/account-deleted.subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/account-deleted.body.txt"
        )
        body_renderer.string_response = "Email Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        result = email.send_account_deletion_email(pyramid_request, user=stub_user)

        assert result == {"username": stub_user.username}
        subject_renderer.assert_()
        body_renderer.assert_(username=stub_user.username)
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                "Email Subject",
                "Email Body",
                recipient=f"{stub_user.username} <{stub_user.email}>",
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
            "email/account-deleted.subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/account-deleted.body.txt"
        )
        body_renderer.string_response = "Email Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        result = email.send_account_deletion_email(pyramid_request, user=stub_user)

        assert result == {"username": stub_user.username}
        subject_renderer.assert_()
        body_renderer.assert_(username=stub_user.username)
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
            "email/primary-email-change.subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/primary-email-change.body.txt"
        )
        body_renderer.string_response = "Email Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        result = email.send_primary_email_change_email(
            pyramid_request,
            stub_user,
            pretend.stub(email="old_email@example.com", verified=True),
        )

        assert result == {
            "username": stub_user.username,
            "old_email": "old_email@example.com",
            "new_email": stub_user.email,
        }
        subject_renderer.assert_()
        body_renderer.assert_(username=stub_user.username)
        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                "Email Subject",
                "Email Body",
                recipient="username <old_email@example.com>",
            )
        ]

    def test_primary_email_change_email_unverified(
        self, pyramid_request, pyramid_config, monkeypatch
    ):

        stub_user = pretend.stub(
            email="new_email@example.com", username="username", name=""
        )
        subject_renderer = pyramid_config.testing_add_renderer(
            "email/primary-email-change.subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/primary-email-change.body.txt"
        )
        body_renderer.string_response = "Email Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        result = email.send_primary_email_change_email(
            pyramid_request,
            stub_user,
            pretend.stub(email="old_email@example.com", verified=False),
        )

        assert result == {
            "username": stub_user.username,
            "old_email": "old_email@example.com",
            "new_email": stub_user.email,
        }
        subject_renderer.assert_()
        body_renderer.assert_(username=stub_user.username)
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
            "email/collaborator-added.subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/collaborator-added.body.txt"
        )
        body_renderer.string_response = "Email Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        result = email.send_collaborator_added_email(
            pyramid_request,
            user=stub_user,
            submitter=stub_submitter_user,
            project_name="test_project",
            role="Owner",
            email_recipients=[stub_user, stub_submitter_user],
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

        assert pyramid_request.task.calls == [
            pretend.call(send_email),
            pretend.call(send_email),
        ]
        assert send_email.delay.calls == [
            pretend.call(
                "Email Subject", "Email Body", recipient="username <email@example.com>"
            ),
            pretend.call(
                "Email Subject",
                "Email Body",
                recipient="submitterusername <submiteremail@example.com>",
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
            "email/collaborator-added.subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/collaborator-added.body.txt"
        )
        body_renderer.string_response = "Email Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        result = email.send_collaborator_added_email(
            pyramid_request,
            user=stub_user,
            submitter=stub_submitter_user,
            project_name="test_project",
            role="Owner",
            email_recipients=[stub_user, stub_submitter_user],
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

        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                "Email Subject",
                "Email Body",
                recipient="submitterusername <submiteremail@example.com>",
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
            "email/added-as-collaborator.subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/added-as-collaborator.body.txt"
        )
        body_renderer.string_response = "Email Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        result = email.send_added_as_collaborator_email(
            pyramid_request,
            submitter=stub_submitter_user,
            project_name="test_project",
            role="Owner",
            user=stub_user,
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

        assert pyramid_request.task.calls == [pretend.call(send_email)]
        assert send_email.delay.calls == [
            pretend.call(
                "Email Subject", "Email Body", recipient="username <email@example.com>"
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
            "email/added-as-collaborator.subject.txt"
        )
        subject_renderer.string_response = "Email Subject"
        body_renderer = pyramid_config.testing_add_renderer(
            "email/added-as-collaborator.body.txt"
        )
        body_renderer.string_response = "Email Body"

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(lambda *args, **kwargs: send_email)
        monkeypatch.setattr(email, "send_email", send_email)

        result = email.send_added_as_collaborator_email(
            pyramid_request,
            submitter=stub_submitter_user,
            project_name="test_project",
            role="Owner",
            user=stub_user,
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

        assert pyramid_request.task.calls == []
        assert send_email.delay.calls == []
