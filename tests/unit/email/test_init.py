# SPDX-License-Identifier: Apache-2.0

import datetime

import celery
import celery.exceptions
import pytest

from pyramid_mailer.exceptions import BadHeaders, EncodingError, InvalidMessage

from warehouse import email
from warehouse.accounts.models import User
from warehouse.email.services import EmailMessage

from ...common.constants import REMOTE_ADDR
from ...common.db.accounts import EmailFactory, UserFactory
from ...common.db.oidc import GitHubPublisherFactory
from ...common.db.organizations import TeamFactory
from ...common.db.packaging import ProjectFactory, ReleaseFactory


@pytest.mark.parametrize(
    ("name", "username", "address", "expected"),
    [
        ("", "", None, "me@example.com"),
        ("", "", "other@example.com", "other@example.com"),
        ("", "foo", None, "foo <me@example.com>"),
        ("bar", "foo", None, "bar <me@example.com>"),
        ("bar", "foo", "other@example.com", "bar <other@example.com>"),
    ],
)
def test_compute_recipient(name, username, address, expected):
    user = UserFactory.build(name=name, username=username)
    email_ = address if address is not None else "me@example.com"
    assert email._compute_recipient(user, email_) == expected


@pytest.mark.parametrize(
    ("unauthenticated_user", "user", "remote_addr", "expected"),
    [
        ("recipient", None, REMOTE_ADDR, False),
        ("other", None, REMOTE_ADDR, True),
        (None, "recipient", REMOTE_ADDR, False),
        (None, "other", REMOTE_ADDR, True),
        (None, None, REMOTE_ADDR, False),
        (None, None, "127.0.0.1", True),
    ],
)
def test_redact_ip(db_request, unauthenticated_user, user, remote_addr, expected):
    user_email = EmailFactory.create()
    users = {"recipient": user_email.user, "other": UserFactory.create()}

    if unauthenticated_user is not None:
        db_request._unauthenticated_userid = users[unauthenticated_user].id
    db_request.user = users.get(user)
    db_request.remote_addr = remote_addr

    assert email._redact_ip(db_request, user_email.email) == expected


def test_redact_ip_email_not_found(db_request):
    assert email._redact_ip(db_request, "missing@example.com") is False


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
        self, name, username, primary_email, address, expected, db_request, send_email
    ):
        user = EmailFactory.create(
            email=primary_email, verified=True, user__name=name, user__username=username
        ).user
        db_request.user = user
        db_request.remote_addr = "10.69.10.69"

        if address is not None:
            address = EmailFactory.create(
                user=user, email=address, verified=True, primary=False
            )

        msg = EmailMessage(subject="My Subject", body_text="My Body")

        email._send_email_to_user(db_request, user, msg, email=address)

        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            expected,
            {
                "sender": None,
                "subject": "My Subject",
                "body_text": "My Body",
                "body_html": None,
            },
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

    @pytest.mark.parametrize(
        ("primary_email", "address"),
        [
            ("email@example.com", None),
            ("email@example.com", "anotheremail@example.com"),
        ],
    )
    def test_doesnt_send_with_unverified(
        self, primary_email, address, db_request, send_email
    ):
        user = EmailFactory.create(
            email=primary_email, verified=address is not None
        ).user

        if address is not None:
            address = EmailFactory.create(
                user=user, email=address, verified=False, primary=False
            )

        msg = EmailMessage(subject="My Subject", body_text="My Body")

        skip_reason = email._send_email_to_user(db_request, user, msg, email=address)

        assert skip_reason == "unverified-email"
        db_request.task.assert_not_called()
        send_email.delay.assert_not_called()

    def test_doesnt_send_without_email_address(self, db_request, send_email):
        """A user with no primary email address is skipped."""
        user = UserFactory.create()

        msg = EmailMessage(subject="My Subject", body_text="My Body")

        skip_reason = email._send_email_to_user(db_request, user, msg)

        assert skip_reason == "no-email-address"
        db_request.task.assert_not_called()
        send_email.delay.assert_not_called()

    def test_doesnt_send_within_repeat_window(
        self, db_request, email_service, send_email, mocker
    ):
        last_sent = mocker.patch.object(
            email_service,
            "last_sent",
            autospec=True,
            return_value=datetime.datetime.now() - datetime.timedelta(seconds=69),
        )

        address = "foo@example.com"
        user = EmailFactory.create(email=address, verified=True).user

        msg = EmailMessage(subject="My Subject", body_text="My Body")

        skip_reason = email._send_email_to_user(
            db_request, user, msg, repeat_window=datetime.timedelta(seconds=420)
        )

        assert skip_reason == "repeat-window"
        last_sent.assert_called_once_with(to=address, subject="My Subject")
        db_request.task.assert_not_called()
        send_email.delay.assert_not_called()

    def test_sends_when_outside_repeat_window(
        self, db_request, email_service, send_email, mocker
    ):
        last_sent = mocker.patch.object(
            email_service,
            "last_sent",
            autospec=True,
            return_value=datetime.datetime.now() - datetime.timedelta(seconds=69),
        )

        user = UserFactory.create(with_verified_primary_email=True)

        msg = EmailMessage(subject="My Subject", body_text="My Body")

        email._send_email_to_user(
            db_request, user, msg, repeat_window=datetime.timedelta(seconds=42)
        )

        last_sent.assert_called_once_with(to=user.email, subject="My Subject")

        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{user.name} <{user.primary_email.email}>",
            {
                "sender": None,
                "subject": "My Subject",
                "body_text": "My Body",
                "body_html": None,
            },
            {
                "tag": "account:email:sent",
                "user_id": user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": user.email,
                    "subject": "My Subject",
                    "redact_ip": False,
                },
            },
        )

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
        self, username, primary_email, address, expected, db_request, send_email
    ):
        user = EmailFactory.create(
            email=primary_email,
            verified=address is not None,
            user__username=username,
            user__name="",
        ).user
        db_request.user = user

        if address is not None:
            address = EmailFactory.create(
                user=user, email=address, verified=False, primary=False
            )

        msg = EmailMessage(subject="My Subject", body_text="My Body")

        email._send_email_to_user(
            db_request, user, msg, email=address, allow_unverified=True
        )

        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            expected,
            {
                "sender": None,
                "subject": "My Subject",
                "body_text": "My Body",
                "body_html": None,
            },
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


class TestSendEmail:
    @pytest.fixture
    def success_event(self):
        return {
            "tag": "account:email:sent",
            "additional": {
                "from_": "noreply@example.com",
                "to": "recipient@example.com",
                "subject": "subject",
                "redact_ip": False,
            },
        }

    @pytest.mark.parametrize("delete_user", [True, False])
    def test_send_email_success(
        self, delete_user, db_request, email_service, success_event, mocker
    ):
        user = UserFactory.create()
        user_id = user.id
        if delete_user:
            db_request.db.delete(user)
            db_request.db.flush()

        email.send_email(
            mocker.sentinel.task,
            db_request,
            "recipient@example.com",
            {"subject": "subject", "body_text": "body", "body_html": None},
            {**success_event, "user_id": user_id},
        )

        [msg] = email_service.mailer.outbox
        assert msg.subject == "subject"
        assert msg.body == "body"
        assert msg.html is None
        assert msg.recipients == ["recipient@example.com"]
        if delete_user:
            assert (
                db_request.db.query(User.Event).filter_by(source_id=user_id).count()
                == 0
            )
        else:
            event = user.events.one()
            assert event.tag == success_event["tag"]
            assert event.additional == success_event["additional"]

    def test_send_email_failure_retry(
        self, pyramid_request, email_service, success_event, mocker
    ):
        exc = Exception()
        sentry_sdk = mocker.patch.object(email, "sentry_sdk", autospec=True)
        mocker.patch.object(email_service, "send", autospec=True, side_effect=exc)
        task = mocker.create_autospec(celery.Task, instance=True)
        task.retry.side_effect = celery.exceptions.Retry

        with pytest.raises(celery.exceptions.Retry):
            email.send_email(
                task,
                pyramid_request,
                "recipient@example.com",
                {"subject": "subject", "body_text": "body", "body_html": None},
                {**success_event, "user_id": mocker.sentinel.user_id},
            )

        sentry_sdk.capture_exception.assert_called_once_with(exc)
        task.retry.assert_called_once_with(exc=exc)

    @pytest.mark.parametrize("exc", [InvalidMessage, BadHeaders, EncodingError])
    def test_send_email_failure_doesnt_retry(
        self, exc, pyramid_request, email_service, success_event, mocker
    ):
        mocker.patch.object(email_service, "send", autospec=True, side_effect=exc)
        task = mocker.create_autospec(celery.Task, instance=True)

        with pytest.raises(exc):
            email.send_email(
                task,
                pyramid_request,
                "recipient@example.com",
                {"subject": "subject", "body_text": "body", "body_html": None},
                {**success_event, "user_id": mocker.sentinel.user_id},
            )

        task.retry.assert_not_called()


class TestSendPasswordResetEmail:
    @pytest.mark.parametrize(
        "email_addr",
        [
            None,
            "other@example.com",
        ],
    )
    def test_send_password_reset_email(
        self,
        email_addr,
        db_request,
        token_service,
        metrics,
        make_email_renderers,
        send_email,
        mocker,
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username_value",
            user__name="name_value",
            user__last_login=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
            user__password_date=datetime.datetime(2026, 1, 2, tzinfo=datetime.UTC),
        ).user
        if email_addr is None:
            user_email = None
        else:
            user_email = EmailFactory.create(
                user=user, email=email_addr, verified=True, primary=False
            )
        db_request.method = "POST"
        mocker.patch.object(token_service, "dumps", autospec=True, return_value="TOKEN")

        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "password-reset"
        )

        db_request.user = user

        result = email.send_password_reset_email(db_request, (user, user_email))

        assert result == {
            "token": "TOKEN",
            "username": user.username,
            "n_hours": token_service.max_age // 60 // 60,
        }
        subject_renderer.assert_()
        body_renderer.assert_(token="TOKEN", username=user.username)
        html_renderer.assert_(token="TOKEN", username=user.username)
        token_service.dumps.assert_called_once_with(
            {
                "action": "password-reset",
                "user.id": str(user.id),
                "user.last_login": str(user.last_login),
                "user.password_date": str(user.password_date),
            }
        )
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            "name_value <" + (user.email if email_addr is None else email_addr) + ">",
            {
                "sender": None,
                "subject": "Email Subject",
                "body_text": "Email Body",
                "body_html": (
                    "<html>\n<head></head>\n"
                    "<body><p>Email HTML Body</p></body>\n</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": ("other@example.com" if user_email else "email@example.com"),
                    "subject": "Email Subject",
                    "redact_ip": False,
                },
            },
        )
        metrics.increment.assert_called_once_with(
            "warehouse.emails.scheduled",
            tags=[
                "template_name:password-reset",
                "allow_unverified:False",
                "repeat_window:none",
            ],
        )

    def test_unverified_email_sends_alt_notice(self, db_request, make_email_renderers):
        unverified_email = EmailFactory.create(verified=False)

        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "password-reset-unverified"
        )

        result = email.send_password_reset_unverified_email(
            db_request, (unverified_email.user, unverified_email)
        )

        assert result == {}
        subject_renderer.assert_()
        body_renderer.assert_()
        html_renderer.assert_()


class TestEmailVerificationEmail:
    def test_email_verification_email(
        self, db_request, token_service, make_email_renderers, send_email, mocker
    ):
        user = EmailFactory.create(email="foo@example.com", user__name="").user
        user_email = EmailFactory.create(
            user=user, email="email@example.com", verified=False, primary=False
        )
        db_request.method = "POST"
        mocker.patch.object(token_service, "dumps", autospec=True, return_value="TOKEN")

        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "verify-email"
        )

        db_request.user = user

        result = email.send_email_verification_email(db_request, (user, user_email))

        assert result == {
            "token": "TOKEN",
            "email_address": user_email.email,
            "n_hours": token_service.max_age // 60 // 60,
        }
        subject_renderer.assert_()
        body_renderer.assert_(token="TOKEN", email_address=user_email.email)
        html_renderer.assert_(token="TOKEN", email_address=user_email.email)
        token_service.dumps.assert_called_once_with(
            {"action": "email-verify", "email.id": user_email.id}
        )
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{user.username} <{user_email.email}>",
            {
                "sender": None,
                "subject": "Email Subject",
                "body_text": "Email Body",
                "body_html": (
                    "<html>\n<head></head>\n"
                    "<body><p>Email HTML Body</p></body>\n</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": user_email.email,
                    "subject": "Email Subject",
                    "redact_ip": False,
                },
            },
        )


class TestNewEmailAddedEmails:
    def test_new_email_added_emails(self, db_request, make_email_renderers, send_email):
        user = EmailFactory.create(email="foo@example.com").user
        user_email = EmailFactory.create(
            user=user, email="email@example.com", verified=False, primary=False
        )
        new_email_address = "new@example.com"
        db_request.method = "POST"

        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "new-email-added"
        )

        result = email.send_new_email_added_email(
            db_request,
            (user, user_email),
            new_email_address=new_email_address,
        )

        assert result == {
            "username": user.username,
            "new_email_address": new_email_address,
        }
        subject_renderer.assert_()
        body_renderer.assert_(new_email_address=new_email_address)
        html_renderer.assert_(new_email_address=new_email_address)
        db_request.task.assert_not_called()
        send_email.delay.assert_not_called()


class TestPasswordChangeEmail:
    def test_password_change_email(self, db_request, make_email_renderers, send_email):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "password-change"
        )

        db_request.user = user

        result = email.send_password_change_email(db_request, user)

        assert result == {"username": user.username}
        subject_renderer.assert_()
        body_renderer.assert_(username=user.username)
        html_renderer.assert_(username=user.username)
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{user.username} <{user.email}>",
            {
                "sender": None,
                "subject": "Email Subject",
                "body_text": "Email Body",
                "body_html": (
                    "<html>\n<head></head>\n"
                    "<body><p>Email HTML Body</p></body>\n</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": user.email,
                    "subject": "Email Subject",
                    "redact_ip": False,
                },
            },
        )

    def test_password_change_email_unverified(
        self, db_request, make_email_renderers, send_email
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=False,
            user__username="username",
            user__name="",
        ).user
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "password-change"
        )

        db_request.user = user

        result = email.send_password_change_email(db_request, user)

        assert result == {"username": user.username}
        subject_renderer.assert_()
        body_renderer.assert_(username=user.username)
        html_renderer.assert_(username=user.username)
        db_request.task.assert_not_called()
        send_email.delay.assert_not_called()


class TestPasswordCompromisedHIBPEmail:
    @pytest.mark.parametrize("verified", [True, False])
    def test_password_compromised_email_hibp(
        self, db_request, verified, make_email_renderers, send_email
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=verified,
            user__username="username",
            user__name="",
        ).user
        make_email_renderers("password-compromised-hibp")

        db_request.user = user

        result = email.send_password_compromised_email_hibp(db_request, user)

        assert result == {}
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{user.username} <{user.email}>",
            {
                "sender": None,
                "subject": "Email Subject",
                "body_text": "Email Body",
                "body_html": (
                    "<html>\n<head></head>\n"
                    "<body><p>Email HTML Body</p></body>\n</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": user.email,
                    "subject": "Email Subject",
                    "redact_ip": False,
                },
            },
        )


class TestTokenLeakEmail:
    @pytest.mark.parametrize("verified", [True, False])
    @pytest.mark.parametrize(
        ("kwargs", "expected_context"),
        [
            (
                {"public_url": "http://example.com", "origin": "github"},
                {
                    "public_url": "http://example.com",
                    "origin": "github",
                    "admin_initiated": False,
                    "reason": None,
                },
            ),
            (
                {"admin_initiated": True, "reason": "Found in a public CI log"},
                {
                    "public_url": None,
                    "origin": None,
                    "admin_initiated": True,
                    "reason": "Found in a public CI log",
                },
            ),
        ],
    )
    def test_token_leak_email(
        self,
        db_request,
        verified,
        kwargs,
        expected_context,
        make_email_renderers,
        send_email,
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=verified,
            user__username="username",
            user__name="",
        ).user

        make_email_renderers("token-compromised-leak")

        result = email.send_token_compromised_email_leak(db_request, user, **kwargs)

        assert result == {"username": "username", **expected_context}
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{user.username} <{user.email}>",
            {
                "sender": None,
                "subject": "Email Subject",
                "body_text": "Email Body",
                "body_html": (
                    "<html>\n<head></head>\n"
                    "<body><p>Email HTML Body</p></body>\n</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": "email@example.com",
                    "subject": "Email Subject",
                    "redact_ip": False,
                },
            },
        )


class TestAccountRecoveryInitiatedEmail:
    @pytest.mark.parametrize("verified", [True, False])
    def test_send_account_recovery_initiated_email(
        self, db_request, verified, make_email_renderers, send_email
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=verified,
            user__username="username",
            user__name="",
        ).user
        user_email = EmailFactory.create(
            user=user, email="recovery@example.com", verified=False, primary=False
        )
        make_email_renderers("account-recovery-initiated")

        db_request.user = user

        result = email.send_account_recovery_initiated_email(
            db_request,
            (user, user_email),
            project_name="project",
            support_issue_link="https://github.com/pypi/support/issues/666",
            token="deadbeef",
        )

        assert result == {
            "project_name": "project",
            "support_issue_link": "https://github.com/pypi/support/issues/666",
            "token": "deadbeef",
            "user": user,
        }
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{user.username} <{user_email.email}>",
            {
                "sender": "support@pypi.org",
                "subject": "Email Subject",
                "body_text": "Email Body",
                "body_html": (
                    "<html>\n<head></head>\n"
                    "<body><p>Email HTML Body</p></body>\n</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": user.id,
                "additional": {
                    "from_": "support@pypi.org",
                    "to": user_email.email,
                    "subject": "Email Subject",
                    "redact_ip": False,
                },
            },
        )


class TestPasswordCompromisedEmail:
    @pytest.mark.parametrize("verified", [True, False])
    def test_password_compromised_email(
        self, db_request, verified, make_email_renderers, send_email
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=verified,
            user__username="username",
            user__name="",
        ).user
        make_email_renderers("password-compromised")

        db_request.user = user

        result = email.send_password_compromised_email(db_request, user)

        assert result == {}
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{user.username} <{user.email}>",
            {
                "sender": None,
                "subject": "Email Subject",
                "body_text": "Email Body",
                "body_html": (
                    "<html>\n<head></head>\n"
                    "<body><p>Email HTML Body</p></body>\n</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": user.email,
                    "subject": "Email Subject",
                    "redact_ip": False,
                },
            },
        )


class TestPasswordResetByAdminEmail:
    @pytest.mark.parametrize("verified", [True, False])
    def test_password_reset_by_admin_email(
        self, db_request, verified, make_email_renderers, send_email
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=verified,
            user__username="username",
            user__name="",
        ).user
        make_email_renderers("password-reset-by-admin")

        db_request.user = user

        result = email.send_password_reset_by_admin_email(db_request, user)

        assert result == {}
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{user.username} <{user.email}>",
            {
                "sender": None,
                "subject": "Email Subject",
                "body_text": "Email Body",
                "body_html": (
                    "<html>\n<head></head>\n"
                    "<body><p>Email HTML Body</p></body>\n</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": user.email,
                    "subject": "Email Subject",
                    "redact_ip": False,
                },
            },
        )


class TestAccountDeletionEmail:
    def test_account_deletion_email(
        self, db_request, metrics, make_email_renderers, send_email
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "account-deleted"
        )

        db_request.user = user

        result = email.send_account_deletion_email(db_request, user)

        assert result == {"username": user.username}
        subject_renderer.assert_()
        body_renderer.assert_(username=user.username)
        html_renderer.assert_(username=user.username)
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{user.username} <{user.email}>",
            {
                "sender": None,
                "subject": "Email Subject",
                "body_text": "Email Body",
                "body_html": (
                    "<html>\n<head></head>\n"
                    "<body><p>Email HTML Body</p></body>\n</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": user.email,
                    "subject": "Email Subject",
                    "redact_ip": False,
                },
            },
        )

        metrics.increment.assert_called_once_with(
            "warehouse.emails.scheduled",
            tags=[
                "template_name:account-deleted",
                "allow_unverified:False",
                "repeat_window:none",
            ],
        )

    def test_account_deletion_email_unverified(
        self, db_request, metrics, make_email_renderers, send_email
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=False,
            user__username="username",
            user__name="",
        ).user
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "account-deleted"
        )

        db_request.user = user

        result = email.send_account_deletion_email(db_request, user)

        assert result == {"username": user.username}
        subject_renderer.assert_()
        body_renderer.assert_(username=user.username)
        html_renderer.assert_(username=user.username)
        db_request.task.assert_not_called()
        send_email.delay.assert_not_called()
        metrics.increment.assert_called_once_with(
            "warehouse.emails.skipped",
            tags=[
                "template_name:account-deleted",
                "allow_unverified:False",
                "repeat_window:none",
                "reason:unverified-email",
            ],
        )


class TestPrimaryEmailChangeEmail:
    def test_primary_email_change_email(
        self, db_request, make_email_renderers, send_email
    ):
        user = EmailFactory.create(
            email="new_email@example.com", user__username="username", user__name=""
        ).user
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "primary-email-change"
        )

        db_request.user = user

        result = email.send_primary_email_change_email(
            db_request,
            (
                user,
                EmailFactory.create(
                    user=user,
                    email="old_email@example.com",
                    verified=True,
                    primary=False,
                ),
            ),
        )

        assert result == {
            "username": user.username,
            "old_email": "old_email@example.com",
            "new_email": user.email,
        }
        subject_renderer.assert_()
        body_renderer.assert_(username=user.username)
        html_renderer.assert_(username=user.username)
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            "username <old_email@example.com>",
            {
                "sender": None,
                "subject": "Email Subject",
                "body_text": "Email Body",
                "body_html": (
                    "<html>\n<head></head>\n"
                    "<body><p>Email HTML Body</p></body>\n</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": "old_email@example.com",
                    "subject": "Email Subject",
                    "redact_ip": False,
                },
            },
        )

    def test_primary_email_change_email_unverified(
        self, db_request, make_email_renderers, send_email
    ):
        user = EmailFactory.create(
            email="new_email@example.com", user__username="username", user__name=""
        ).user
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "primary-email-change"
        )

        db_request.user = user

        result = email.send_primary_email_change_email(
            db_request,
            (
                user,
                EmailFactory.create(
                    user=user,
                    email="old_email@example.com",
                    verified=False,
                    primary=False,
                ),
            ),
        )

        assert result == {
            "username": user.username,
            "old_email": "old_email@example.com",
            "new_email": user.email,
        }
        subject_renderer.assert_()
        body_renderer.assert_(username=user.username)
        html_renderer.assert_(username=user.username)
        db_request.task.assert_not_called()
        send_email.delay.assert_not_called()


class TestSendNewOrganizationRequestedEmail:
    def test_send_new_organization_requested_email(
        self, db_request, make_email_renderers, send_email
    ):
        initiator_user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        organization_name = "example"

        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "new-organization-requested"
        )

        db_request.user = initiator_user

        result = email.send_new_organization_requested_email(
            db_request,
            initiator_user,
            organization_name=organization_name,
        )

        assert result == {"organization_name": organization_name}
        subject_renderer.assert_(organization_name=organization_name)
        body_renderer.assert_(organization_name=organization_name)
        html_renderer.assert_(organization_name=organization_name)
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{initiator_user.username} <{initiator_user.email}>",
            {
                "sender": None,
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


class TestSendNewOrganizationApprovedEmail:
    def test_send_new_organization_approved_email(
        self, db_request, make_email_renderers, send_email
    ):
        initiator_user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        organization_name = "example"
        organization_type = "Community"
        message = "example message"

        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "new-organization-approved"
        )

        db_request.user = initiator_user

        result = email.send_new_organization_approved_email(
            db_request,
            initiator_user,
            organization_name=organization_name,
            organization_type=organization_type,
            message=message,
        )

        assert result == {
            "organization_name": organization_name,
            "organization_type": organization_type,
            "message": message,
        }
        subject_renderer.assert_(
            organization_name=organization_name,
            organization_type=organization_type,
            message=message,
        )
        body_renderer.assert_(
            organization_name=organization_name,
            organization_type=organization_type,
            message=message,
        )
        html_renderer.assert_(
            organization_name=organization_name,
            message=message,
        )
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{initiator_user.username} <{initiator_user.email}>",
            {
                "sender": None,
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

    @pytest.mark.parametrize(
        ("organization_type", "expects_action_required"),
        [
            ("Company", True),
            ("Community", False),
        ],
    )
    def test_renders_action_required_only_for_company(
        self,
        db_request,
        pyramid_config,
        organization_type,
        expects_action_required,
        send_email,
    ):
        """
        The rendered email should only nag Company organizations to buy a
        seat -- Community organizations shouldn't see that content at all.
        """
        initiator_user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        organization_name = "example"

        pyramid_config.include("pyramid_jinja2")
        pyramid_config.add_settings({"jinja2.newstyle": True})
        pyramid_config.add_settings({"jinja2.i18n.domain": "messages"})
        pyramid_config.add_jinja2_renderer(".html")
        pyramid_config.add_jinja2_renderer(".txt")
        pyramid_config.add_jinja2_search_path("warehouse:templates", name=".html")
        pyramid_config.add_jinja2_search_path("warehouse:templates", name=".txt")
        pyramid_config.add_route(
            "manage.organization.activate_subscription",
            "/manage/organization/{organization_name}/subscription/activate/",
        )
        pyramid_config.add_route(
            "manage.organization.settings",
            "/manage/organization/{organization_name}/settings/",
        )

        db_request.user = initiator_user
        db_request.registry.settings["warehouse.domain"] = "pypi.org"
        db_request.environ.update(
            {
                "wsgi.url_scheme": "https",
                "SERVER_NAME": "pypi.org",
                "SERVER_PORT": "443",
                "HTTP_HOST": "pypi.org",
            }
        )

        email.send_new_organization_approved_email(
            db_request,
            initiator_user,
            organization_name=organization_name,
            organization_type=organization_type,
            message="example message",
        )

        (_, msg, _), _ = send_email.delay.call_args
        subject, body_text, body_html = (
            msg["subject"],
            msg["body_text"],
            msg["body_html"],
        )

        assert ("Action Required" in subject) is expects_action_required
        assert ("Action Required" in body_text) is expects_action_required
        assert ("Action Required" in body_html) is expects_action_required
        assert ("activate" in body_text) is expects_action_required
        assert ("activate" in body_html) is expects_action_required
        management_url = (
            f"https://pypi.org/manage/organization/{organization_name}/settings/"
        )
        assert management_url in body_text
        assert f'href="{management_url}"' in body_html


class TestSendNewOrganizationRequestMoreInfoEmail:
    def test_send_new_organization_moreinformationneeded_email(
        self, db_request, make_email_renderers, send_email
    ):
        initiator_user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        organization_name = "example"
        organization_application_id = "deadbeef-dead-beef-dead-beefdeadbeef"
        message = "example message"

        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "new-organization-moreinformationneeded"
        )

        db_request.user = initiator_user

        result = email.send_new_organization_moreinformationneeded_email(
            db_request,
            initiator_user,
            organization_name=organization_name,
            organization_application_id=organization_application_id,
            message=message,
        )

        assert result == {
            "organization_name": organization_name,
            "organization_application_id": organization_application_id,
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
        send_email.delay.assert_called_once_with(
            f"{initiator_user.username} <{initiator_user.email}>",
            {
                "sender": None,
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


class TestSendNewOrganizationDeclinedEmail:
    def test_send_new_organization_declined_email(
        self, db_request, make_email_renderers, send_email
    ):
        initiator_user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        organization_name = "example"
        message = "example message"

        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "new-organization-declined"
        )

        db_request.user = initiator_user

        result = email.send_new_organization_declined_email(
            db_request,
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
        send_email.delay.assert_called_once_with(
            f"{initiator_user.username} <{initiator_user.email}>",
            {
                "sender": None,
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


class TestOrganizationProjectEmails:
    @pytest.fixture
    def _organization_project(self, pyramid_user):
        self.user = pyramid_user
        self.organization_name = "exampleorganization"
        self.project_name = "exampleproject"

    @pytest.mark.usefixtures("_organization_project")
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
        make_email_renderers,
        send_email,
        email_template_name,
        send_organization_project_email,
    ):
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            email_template_name
        )

        submitter_username = "submitter"

        result = send_organization_project_email(
            db_request,
            self.user,
            organization_name=self.organization_name,
            project_name=self.project_name,
            submitter_username=submitter_username,
        )

        assert result == {
            "organization_name": self.organization_name,
            "project_name": self.project_name,
            "submitter": submitter_username,
        }
        subject_renderer.assert_(**result)
        body_renderer.assert_(**result)
        html_renderer.assert_(**result)
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{self.user.name} <{self.user.email}>",
            {
                "sender": None,
                "subject": subject_renderer.string_response,
                "body_text": body_renderer.string_response,
                "body_html": (
                    f"<html>\n"
                    f"<head></head>\n"
                    f"<body>{html_renderer.string_response}</body>\n"
                    f"</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": self.user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": self.user.email,
                    "subject": subject_renderer.string_response,
                    "redact_ip": False,
                },
            },
        )


class TestOrganizationMemberEmails:
    @pytest.fixture
    def _organization_invite(self, pyramid_user):
        self.initiator_user = pyramid_user
        self.user = UserFactory.create()
        EmailFactory.create(user=self.user, verified=True)
        self.desired_role = "Manager"
        self.organization_name = "example"
        self.message = "test message"
        self.email_token = "token"
        self.token_age = 72 * 60 * 60

    @pytest.mark.usefixtures("_organization_invite")
    def test_send_organization_member_invited_email(
        self,
        db_request,
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
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{self.initiator_user.name} <{self.initiator_user.email}>",
            {
                "sender": None,
                "subject": subject_renderer.string_response,
                "body_text": body_renderer.string_response,
                "body_html": (
                    f"<html>\n"
                    f"<head></head>\n"
                    f"<body>{html_renderer.string_response}</body>\n"
                    f"</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": self.initiator_user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": self.initiator_user.email,
                    "subject": subject_renderer.string_response,
                    "redact_ip": False,
                },
            },
        )

    @pytest.mark.usefixtures("_organization_invite")
    def test_send_organization_role_verification_email(
        self,
        db_request,
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
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{self.user.name} <{self.user.email}>",
            {
                "sender": None,
                "subject": subject_renderer.string_response,
                "body_text": body_renderer.string_response,
                "body_html": (
                    f"<html>\n"
                    f"<head></head>\n"
                    f"<body>{html_renderer.string_response}</body>\n"
                    f"</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": self.user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": self.user.email,
                    "subject": subject_renderer.string_response,
                    "redact_ip": True,
                },
            },
        )

    @pytest.mark.usefixtures("_organization_invite")
    def test_send_organization_member_invite_canceled_email(
        self,
        db_request,
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
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{self.initiator_user.name} <{self.initiator_user.email}>",
            {
                "sender": None,
                "subject": subject_renderer.string_response,
                "body_text": body_renderer.string_response,
                "body_html": (
                    f"<html>\n"
                    f"<head></head>\n"
                    f"<body>{html_renderer.string_response}</body>\n"
                    f"</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": self.initiator_user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": self.initiator_user.email,
                    "subject": subject_renderer.string_response,
                    "redact_ip": False,
                },
            },
        )

    @pytest.mark.usefixtures("_organization_invite")
    def test_send_canceled_as_invited_organization_member_email(
        self,
        db_request,
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
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{self.user.name} <{self.user.email}>",
            {
                "sender": None,
                "subject": subject_renderer.string_response,
                "body_text": body_renderer.string_response,
                "body_html": (
                    f"<html>\n"
                    f"<head></head>\n"
                    f"<body>{html_renderer.string_response}</body>\n"
                    f"</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": self.user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": self.user.email,
                    "subject": subject_renderer.string_response,
                    "redact_ip": True,
                },
            },
        )

    @pytest.mark.usefixtures("_organization_invite")
    def test_send_organization_member_invite_declined_email(
        self,
        db_request,
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
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{self.initiator_user.name} <{self.initiator_user.email}>",
            {
                "sender": None,
                "subject": subject_renderer.string_response,
                "body_text": body_renderer.string_response,
                "body_html": (
                    f"<html>\n"
                    f"<head></head>\n"
                    f"<body>{html_renderer.string_response}</body>\n"
                    f"</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": self.initiator_user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": self.initiator_user.email,
                    "subject": subject_renderer.string_response,
                    "redact_ip": False,
                },
            },
        )

    @pytest.mark.usefixtures("_organization_invite")
    def test_send_declined_as_invited_organization_member_email(
        self,
        db_request,
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
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{self.user.name} <{self.user.email}>",
            {
                "sender": None,
                "subject": subject_renderer.string_response,
                "body_text": body_renderer.string_response,
                "body_html": (
                    f"<html>\n"
                    f"<head></head>\n"
                    f"<body>{html_renderer.string_response}</body>\n"
                    f"</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": self.user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": self.user.email,
                    "subject": subject_renderer.string_response,
                    "redact_ip": True,
                },
            },
        )

    @pytest.mark.usefixtures("_organization_invite")
    def test_send_organization_member_added_email(
        self,
        db_request,
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
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{self.initiator_user.name} <{self.initiator_user.email}>",
            {
                "sender": None,
                "subject": subject_renderer.string_response,
                "body_text": body_renderer.string_response,
                "body_html": (
                    f"<html>\n"
                    f"<head></head>\n"
                    f"<body>{html_renderer.string_response}</body>\n"
                    f"</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": self.initiator_user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": self.initiator_user.email,
                    "subject": subject_renderer.string_response,
                    "redact_ip": False,
                },
            },
        )

    @pytest.mark.usefixtures("_organization_invite")
    def test_send_added_as_organization_email(
        self,
        db_request,
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
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{self.user.name} <{self.user.email}>",
            {
                "sender": None,
                "subject": subject_renderer.string_response,
                "body_text": body_renderer.string_response,
                "body_html": (
                    f"<html>\n"
                    f"<head></head>\n"
                    f"<body>{html_renderer.string_response}</body>\n"
                    f"</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": self.user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": self.user.email,
                    "subject": subject_renderer.string_response,
                    "redact_ip": True,
                },
            },
        )

    @pytest.mark.usefixtures("_organization_invite")
    def test_send_organization_member_removed_email(
        self,
        db_request,
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
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{self.initiator_user.name} <{self.initiator_user.email}>",
            {
                "sender": None,
                "subject": subject_renderer.string_response,
                "body_text": body_renderer.string_response,
                "body_html": (
                    f"<html>\n"
                    f"<head></head>\n"
                    f"<body>{html_renderer.string_response}</body>\n"
                    f"</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": self.initiator_user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": self.initiator_user.email,
                    "subject": subject_renderer.string_response,
                    "redact_ip": False,
                },
            },
        )

    @pytest.mark.usefixtures("_organization_invite")
    def test_send_removed_as_organization_email(
        self,
        db_request,
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
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{self.user.name} <{self.user.email}>",
            {
                "sender": None,
                "subject": subject_renderer.string_response,
                "body_text": body_renderer.string_response,
                "body_html": (
                    f"<html>\n"
                    f"<head></head>\n"
                    f"<body>{html_renderer.string_response}</body>\n"
                    f"</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": self.user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": self.user.email,
                    "subject": subject_renderer.string_response,
                    "redact_ip": True,
                },
            },
        )

    @pytest.mark.usefixtures("_organization_invite")
    def test_send_organization_member_role_changed_email(
        self,
        db_request,
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
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{self.initiator_user.name} <{self.initiator_user.email}>",
            {
                "sender": None,
                "subject": subject_renderer.string_response,
                "body_text": body_renderer.string_response,
                "body_html": (
                    f"<html>\n"
                    f"<head></head>\n"
                    f"<body>{html_renderer.string_response}</body>\n"
                    f"</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": self.initiator_user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": self.initiator_user.email,
                    "subject": subject_renderer.string_response,
                    "redact_ip": False,
                },
            },
        )

    @pytest.mark.usefixtures("_organization_invite")
    def test_send_role_changed_as_organization_email(
        self,
        db_request,
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
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{self.user.name} <{self.user.email}>",
            {
                "sender": None,
                "subject": subject_renderer.string_response,
                "body_text": body_renderer.string_response,
                "body_html": (
                    f"<html>\n"
                    f"<head></head>\n"
                    f"<body>{html_renderer.string_response}</body>\n"
                    f"</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": self.user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": self.user.email,
                    "subject": subject_renderer.string_response,
                    "redact_ip": True,
                },
            },
        )


class TestOrganizationUpdateEmails:
    @pytest.fixture
    def _organization_update(self, pyramid_user):
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

    @pytest.mark.usefixtures("_organization_update")
    def test_send_organization_renamed_email(
        self,
        db_request,
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
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{self.user.name} <{self.user.email}>",
            {
                "sender": None,
                "subject": subject_renderer.string_response,
                "body_text": body_renderer.string_response,
                "body_html": (
                    f"<html>\n"
                    f"<head></head>\n"
                    f"<body>{html_renderer.string_response}</body>\n"
                    f"</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": self.user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": self.user.email,
                    "subject": subject_renderer.string_response,
                    "redact_ip": True,
                },
            },
        )


class TestOrganizationRenameEmails:
    @pytest.fixture
    def _organization_rename(self, pyramid_user):
        self.user = UserFactory.create()
        EmailFactory.create(user=self.user, verified=True)
        self.organization_name = "example"
        self.previous_organization_name = "examplegroup"

    @pytest.mark.usefixtures("_organization_rename")
    def test_send_organization_renamed_email(
        self,
        db_request,
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
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{self.user.name} <{self.user.email}>",
            {
                "sender": None,
                "subject": subject_renderer.string_response,
                "body_text": body_renderer.string_response,
                "body_html": (
                    f"<html>\n"
                    f"<head></head>\n"
                    f"<body>{html_renderer.string_response}</body>\n"
                    f"</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": self.user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": self.user.email,
                    "subject": subject_renderer.string_response,
                    "redact_ip": True,
                },
            },
        )


class TestOrganizationSubscriptionRequiredEmail:
    def test_send_organization_subscription_required_email(
        self,
        db_request,
        pyramid_user,
        make_email_renderers,
        send_email,
    ):
        user = UserFactory.create()
        EmailFactory.create(user=user, verified=True)
        organization_name = "example"

        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "organization-subscription-required"
        )

        result = email.send_organization_subscription_required_email(
            db_request,
            user,
            organization_name=organization_name,
        )

        assert result == {
            "username": user.username,
            "organization_name": organization_name,
        }
        subject_renderer.assert_(**result)
        body_renderer.assert_(**result)
        html_renderer.assert_(**result)
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{user.name} <{user.email}>",
            {
                "sender": None,
                "subject": subject_renderer.string_response,
                "body_text": body_renderer.string_response,
                "body_html": (
                    f"<html>\n"
                    f"<head></head>\n"
                    f"<body>{html_renderer.string_response}</body>\n"
                    f"</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": user.email,
                    "subject": subject_renderer.string_response,
                    "redact_ip": True,
                },
            },
        )


class TestOrganizationDeleteEmails:
    @pytest.fixture
    def _organization_delete(self, pyramid_user):
        self.user = UserFactory.create()
        EmailFactory.create(user=self.user, verified=True)
        self.organization_name = "example"

    @pytest.mark.usefixtures("_organization_delete")
    def test_send_organization_deleted_email(
        self,
        db_request,
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
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{self.user.name} <{self.user.email}>",
            {
                "sender": None,
                "subject": subject_renderer.string_response,
                "body_text": body_renderer.string_response,
                "body_html": (
                    f"<html>\n"
                    f"<head></head>\n"
                    f"<body>{html_renderer.string_response}</body>\n"
                    f"</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": self.user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": self.user.email,
                    "subject": subject_renderer.string_response,
                    "redact_ip": True,
                },
            },
        )


class TestTeamMemberEmails:
    @pytest.fixture
    def _team(self, pyramid_user):
        self.user = UserFactory.create()
        EmailFactory.create(user=self.user, verified=True)
        self.submitter = pyramid_user
        self.organization_name = "exampleorganization"
        self.team_name = "Example Team"

    @pytest.mark.usefixtures("_team")
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
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{recipient.name} <{recipient.email}>",
            {
                "sender": None,
                "subject": subject_renderer.string_response,
                "body_text": body_renderer.string_response,
                "body_html": (
                    f"<html>\n"
                    f"<head></head>\n"
                    f"<body>{html_renderer.string_response}</body>\n"
                    f"</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": recipient.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": recipient.email,
                    "subject": subject_renderer.string_response,
                    "redact_ip": recipient != self.submitter,
                },
            },
        )


class TestTeamEmails:
    @pytest.fixture
    def _team(self, pyramid_user):
        self.user = pyramid_user
        self.organization_name = "exampleorganization"
        self.team_name = "Example Team"

    @pytest.mark.usefixtures("_team")
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
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{self.user.name} <{self.user.email}>",
            {
                "sender": None,
                "subject": subject_renderer.string_response,
                "body_text": body_renderer.string_response,
                "body_html": (
                    f"<html>\n"
                    f"<head></head>\n"
                    f"<body>{html_renderer.string_response}</body>\n"
                    f"</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": self.user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": self.user.email,
                    "subject": subject_renderer.string_response,
                    "redact_ip": False,
                },
            },
        )


class TestCollaboratorAddedEmail:
    def test_collaborator_added_email(
        self, db_request, make_email_renderers, send_email, mocker
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        submitter_user = EmailFactory.create(
            email="submiteremail@example.com",
            verified=True,
            user__username="submitterusername",
            user__name="",
        ).user
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "collaborator-added"
        )

        db_request.user = submitter_user

        result = email.send_collaborator_added_email(
            db_request,
            [user, submitter_user],
            user=user,
            submitter=submitter_user,
            project_name="test_project",
            role="Owner",
        )

        assert result == {
            "username": user.username,
            "project": "test_project",
            "role": "Owner",
            "submitter": submitter_user.username,
        }
        subject_renderer.assert_()
        body_renderer.assert_(username=user.username)
        body_renderer.assert_(project="test_project")
        body_renderer.assert_(role="Owner")
        body_renderer.assert_(submitter=submitter_user.username)
        html_renderer.assert_(username=user.username)
        html_renderer.assert_(project="test_project")
        html_renderer.assert_(role="Owner")
        html_renderer.assert_(submitter=submitter_user.username)

        assert db_request.task.call_args_list == [
            mocker.call(send_email),
            mocker.call(send_email),
        ]
        assert send_email.delay.call_args_list == [
            mocker.call(
                "username <email@example.com>",
                {
                    "sender": None,
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "email@example.com",
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
            mocker.call(
                "submitterusername <submiteremail@example.com>",
                {
                    "sender": None,
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
                        "from_": "noreply@example.com",
                        "to": "submiteremail@example.com",
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            ),
        ]

    def test_collaborator_added_email_unverified(
        self, db_request, make_email_renderers, send_email
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=False,
            user__username="username",
            user__name="",
        ).user
        submitter_user = EmailFactory.create(
            email="submiteremail@example.com",
            verified=True,
            user__username="submitterusername",
            user__name="",
        ).user
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "collaborator-added"
        )

        db_request.user = submitter_user

        result = email.send_collaborator_added_email(
            db_request,
            [user, submitter_user],
            user=user,
            submitter=submitter_user,
            project_name="test_project",
            role="Owner",
        )

        assert result == {
            "username": user.username,
            "project": "test_project",
            "role": "Owner",
            "submitter": submitter_user.username,
        }
        subject_renderer.assert_()
        body_renderer.assert_(username=user.username)
        body_renderer.assert_(project="test_project")
        body_renderer.assert_(role="Owner")
        body_renderer.assert_(submitter=submitter_user.username)
        html_renderer.assert_(username=user.username)
        html_renderer.assert_(project="test_project")
        html_renderer.assert_(role="Owner")
        html_renderer.assert_(submitter=submitter_user.username)

        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            "submitterusername <submiteremail@example.com>",
            {
                "sender": None,
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
                    "from_": "noreply@example.com",
                    "to": "submiteremail@example.com",
                    "subject": "Email Subject",
                    "redact_ip": False,
                },
            },
        )


class TestProjectRoleVerificationEmail:
    def test_project_role_verification_email(
        self, db_request, token_service, make_email_renderers, send_email
    ):
        user = UserFactory.create()
        EmailFactory.create(
            email="email@example.com",
            primary=True,
            verified=True,
            public=True,
            user=user,
        )

        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "verify-project-role"
        )

        db_request.user = user

        result = email.send_project_role_verification_email(
            db_request,
            user,
            desired_role="Maintainer",
            initiator_username="initiating_user",
            project_name="project_name",
            email_token="TOKEN",
            token_age=token_service.max_age,
        )

        assert result == {
            "desired_role": "Maintainer",
            "email_address": user.email,
            "initiator_username": "initiating_user",
            "n_hours": token_service.max_age // 60 // 60,
            "project_name": "project_name",
            "token": "TOKEN",
        }
        subject_renderer.assert_()
        body_renderer.assert_(token="TOKEN", email_address=user.email)
        html_renderer.assert_(token="TOKEN", email_address=user.email)
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{user.name} <{user.email}>",
            {
                "sender": None,
                "subject": "Email Subject",
                "body_text": "Email Body",
                "body_html": (
                    "<html>\n<head></head>\n"
                    "<body><p>Email HTML Body</p></body>\n</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": "email@example.com",
                    "subject": "Email Subject",
                    "redact_ip": False,
                },
            },
        )


class TestAddedAsCollaboratorEmail:
    def test_added_as_collaborator_email(
        self, db_request, make_email_renderers, send_email
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        submitter_user = UserFactory.create(username="submitterusername")
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "added-as-collaborator"
        )

        db_request.user = submitter_user

        result = email.send_added_as_collaborator_email(
            db_request,
            user,
            submitter=submitter_user,
            project_name="test_project",
            role="Owner",
        )

        assert result == {
            "project_name": "test_project",
            "role": "Owner",
            "initiator_username": submitter_user.username,
        }
        subject_renderer.assert_()
        body_renderer.assert_(initiator_username=submitter_user.username)
        body_renderer.assert_(project_name="test_project")
        body_renderer.assert_(role="Owner")
        html_renderer.assert_(initiator_username=submitter_user.username)
        html_renderer.assert_(project_name="test_project")
        html_renderer.assert_(role="Owner")

        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            "username <email@example.com>",
            {
                "sender": None,
                "subject": "Email Subject",
                "body_text": "Email Body",
                "body_html": (
                    "<html>\n<head></head>\n"
                    "<body><p>Email HTML Body</p></body>\n</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": "email@example.com",
                    "subject": "Email Subject",
                    "redact_ip": True,
                },
            },
        )

    def test_added_as_collaborator_email_unverified(
        self, db_request, make_email_renderers, send_email
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=False,
            user__username="username",
            user__name="",
        ).user
        submitter_user = UserFactory.create(username="submitterusername")
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "added-as-collaborator"
        )

        db_request.user = submitter_user

        result = email.send_added_as_collaborator_email(
            db_request,
            user,
            submitter=submitter_user,
            project_name="test_project",
            role="Owner",
        )

        assert result == {
            "project_name": "test_project",
            "role": "Owner",
            "initiator_username": submitter_user.username,
        }
        subject_renderer.assert_()
        body_renderer.assert_(initiator_username=submitter_user.username)
        body_renderer.assert_(project_name="test_project")
        body_renderer.assert_(role="Owner")
        html_renderer.assert_(initiator_username=submitter_user.username)
        html_renderer.assert_(project_name="test_project")
        html_renderer.assert_(role="Owner")

        db_request.task.assert_not_called()
        send_email.delay.assert_not_called()


class TestCollaboratorRemovedEmail:
    def test_collaborator_removed_email(
        self, db_request, make_email_renderers, send_email, mocker
    ):
        removed_user = UserFactory.create()
        EmailFactory.create(primary=True, verified=True, public=True, user=removed_user)
        submitter_user = UserFactory.create()
        EmailFactory.create(
            primary=True, verified=True, public=True, user=submitter_user
        )
        db_request.user = submitter_user

        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "collaborator-removed"
        )

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

        assert db_request.task.call_args_list == [
            mocker.call(send_email),
            mocker.call(send_email),
        ]
        assert send_email.delay.call_args_list == [
            mocker.call(
                f"{removed_user.name} <{removed_user.primary_email.email}>",
                {
                    "sender": None,
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
                        "from_": "noreply@example.com",
                        "to": removed_user.primary_email.email,
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
            mocker.call(
                f"{submitter_user.name} <{submitter_user.primary_email.email}>",
                {
                    "sender": None,
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
                        "from_": "noreply@example.com",
                        "to": submitter_user.primary_email.email,
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            ),
        ]


class TestRemovedAsCollaboratorEmail:
    def test_removed_as_collaborator_email(
        self, db_request, make_email_renderers, send_email
    ):
        removed_user = UserFactory.create()
        EmailFactory.create(primary=True, verified=True, public=True, user=removed_user)
        submitter_user = UserFactory.create()
        EmailFactory.create(
            primary=True, verified=True, public=True, user=submitter_user
        )
        db_request.user = submitter_user

        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "removed-as-collaborator"
        )

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

        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{removed_user.name} <{removed_user.primary_email.email}>",
            {
                "sender": None,
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
                    "from_": "noreply@example.com",
                    "to": removed_user.primary_email.email,
                    "subject": "Email Subject",
                    "redact_ip": True,
                },
            },
        )


class TestRoleChangedEmail:
    def test_role_changed_email(
        self, db_request, make_email_renderers, send_email, mocker
    ):
        changed_user = UserFactory.create()
        EmailFactory.create(primary=True, verified=True, public=True, user=changed_user)
        submitter_user = UserFactory.create()
        EmailFactory.create(
            primary=True, verified=True, public=True, user=submitter_user
        )
        db_request.user = submitter_user

        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "collaborator-role-changed"
        )

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

        assert db_request.task.call_args_list == [
            mocker.call(send_email),
            mocker.call(send_email),
        ]
        assert send_email.delay.call_args_list == [
            mocker.call(
                f"{changed_user.name} <{changed_user.primary_email.email}>",
                {
                    "sender": None,
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
                        "from_": "noreply@example.com",
                        "to": changed_user.primary_email.email,
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
            mocker.call(
                f"{submitter_user.name} <{submitter_user.primary_email.email}>",
                {
                    "sender": None,
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
                        "from_": "noreply@example.com",
                        "to": submitter_user.primary_email.email,
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            ),
        ]


class TestRoleChangedAsCollaboratorEmail:
    def test_role_changed_as_collaborator_email(
        self, db_request, make_email_renderers, send_email
    ):
        changed_user = UserFactory.create()
        EmailFactory.create(primary=True, verified=True, public=True, user=changed_user)
        submitter_user = UserFactory.create()
        EmailFactory.create(
            primary=True, verified=True, public=True, user=submitter_user
        )
        db_request.user = submitter_user

        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "role-changed-as-collaborator"
        )

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

        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{changed_user.name} <{changed_user.primary_email.email}>",
            {
                "sender": None,
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
                    "from_": "noreply@example.com",
                    "to": changed_user.primary_email.email,
                    "subject": "Email Subject",
                    "redact_ip": True,
                },
            },
        )


class TestTeamCollaboratorEmails:
    @pytest.fixture
    def _team(self, pyramid_user):
        self.user = UserFactory.create()
        EmailFactory.create(user=self.user, verified=True)
        self.submitter = pyramid_user
        self.team = TeamFactory.create(name="Example Team")
        self.project_name = "exampleproject"
        self.role = "Admin"

    @pytest.mark.usefixtures("_team")
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
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{self.user.name} <{self.user.email}>",
            {
                "sender": None,
                "subject": subject_renderer.string_response,
                "body_text": body_renderer.string_response,
                "body_html": (
                    f"<html>\n"
                    f"<head></head>\n"
                    f"<body>{html_renderer.string_response}</body>\n"
                    f"</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": self.user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": self.user.email,
                    "subject": subject_renderer.string_response,
                    "redact_ip": True,
                },
            },
        )


class TestRemovedProjectEmail:
    def test_removed_project_email_to_maintainer(
        self, db_request, make_email_renderers, send_email, mocker
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        submitter_user = EmailFactory.create(
            email="submiteremail@example.com",
            verified=True,
            user__username="submitterusername",
            user__name="",
        ).user
        subject_renderer, body_renderer, _html_renderer = make_email_renderers(
            "removed-project"
        )

        db_request.user = submitter_user

        result = email.send_removed_project_email(
            db_request,
            [user, submitter_user],
            project_name="test_project",
            submitter_name=submitter_user.username,
            submitter_role="Owner",
            recipient_role="Maintainer",
        )

        assert result == {
            "project_name": "test_project",
            "submitter_name": submitter_user.username,
            "submitter_role": "owner",
            "recipient_role_descr": "a maintainer",
        }

        subject_renderer.assert_(project_name="test_project")
        body_renderer.assert_(project_name="test_project")
        body_renderer.assert_(submitter_name=submitter_user.username)
        body_renderer.assert_(submitter_role="owner")
        body_renderer.assert_(recipient_role_descr="a maintainer")

        assert db_request.task.call_args_list == [
            mocker.call(send_email),
            mocker.call(send_email),
        ]

        assert send_email.delay.call_args_list == [
            mocker.call(
                "username <email@example.com>",
                {
                    "sender": None,
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "email@example.com",
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
            mocker.call(
                "submitterusername <submiteremail@example.com>",
                {
                    "sender": None,
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
                        "from_": "noreply@example.com",
                        "to": "submiteremail@example.com",
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            ),
        ]

    def test_removed_project_email_to_owner(
        self, db_request, make_email_renderers, send_email, mocker
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        submitter_user = EmailFactory.create(
            email="submiteremail@example.com",
            verified=True,
            user__username="submitterusername",
            user__name="",
        ).user
        subject_renderer, body_renderer, _html_renderer = make_email_renderers(
            "removed-project"
        )

        db_request.user = submitter_user

        result = email.send_removed_project_email(
            db_request,
            [user, submitter_user],
            project_name="test_project",
            submitter_name=submitter_user.username,
            submitter_role="Owner",
            recipient_role="Owner",
        )

        assert result == {
            "project_name": "test_project",
            "submitter_name": submitter_user.username,
            "submitter_role": "owner",
            "recipient_role_descr": "an owner",
        }

        subject_renderer.assert_(project_name="test_project")
        body_renderer.assert_(project_name="test_project")
        body_renderer.assert_(submitter_name=submitter_user.username)
        body_renderer.assert_(submitter_role="owner")
        body_renderer.assert_(recipient_role_descr="an owner")

        assert db_request.task.call_args_list == [
            mocker.call(send_email),
            mocker.call(send_email),
        ]

        assert send_email.delay.call_args_list == [
            mocker.call(
                "username <email@example.com>",
                {
                    "sender": None,
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "email@example.com",
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
            mocker.call(
                "submitterusername <submiteremail@example.com>",
                {
                    "sender": None,
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
        self, db_request, make_email_renderers, send_email, mocker
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        submitter_user = EmailFactory.create(
            email="submiteremail@example.com",
            verified=True,
            user__username="submitterusername",
            user__name="",
        ).user

        subject_renderer, body_renderer, _html_renderer = make_email_renderers(
            "yanked-project-release"
        )

        db_request.user = submitter_user

        release = ReleaseFactory.build(
            version="0.0.0",
            project=ProjectFactory.build(name="test_project"),
            created=datetime.datetime(2017, 2, 5, 0, 0, 0, 0),
            yanked_reason="Yanky Doodle went to town",
        )

        result = email.send_yanked_project_release_email(
            db_request,
            [user, submitter_user],
            release=release,
            submitter_name=submitter_user.username,
            submitter_role="Owner",
            recipient_role="Maintainer",
        )

        assert result == {
            "project": release.project.name,
            "release": release.version,
            "release_date": release.created.strftime("%Y-%m-%d"),
            "submitter": submitter_user.username,
            "submitter_role": "owner",
            "recipient_role_descr": "a maintainer",
            "yanked_reason": "Yanky Doodle went to town",
        }

        subject_renderer.assert_(project="test_project")
        subject_renderer.assert_(release="0.0.0")
        body_renderer.assert_(project="test_project")
        body_renderer.assert_(release="0.0.0")
        body_renderer.assert_(release_date=release.created.strftime("%Y-%m-%d"))
        body_renderer.assert_(submitter=submitter_user.username)
        body_renderer.assert_(submitter_role="owner")
        body_renderer.assert_(recipient_role_descr="a maintainer")

        assert db_request.task.call_args_list == [
            mocker.call(send_email),
            mocker.call(send_email),
        ]

        assert send_email.delay.call_args_list == [
            mocker.call(
                "username <email@example.com>",
                {
                    "sender": None,
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "email@example.com",
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
            mocker.call(
                "submitterusername <submiteremail@example.com>",
                {
                    "sender": None,
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
                        "from_": "noreply@example.com",
                        "to": "submiteremail@example.com",
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            ),
        ]

    def test_send_yanked_project_release_email_to_owner(
        self, db_request, make_email_renderers, send_email, mocker
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        submitter_user = EmailFactory.create(
            email="submiteremail@example.com",
            verified=True,
            user__username="submitterusername",
            user__name="",
        ).user

        subject_renderer, body_renderer, _html_renderer = make_email_renderers(
            "yanked-project-release"
        )

        db_request.user = submitter_user

        release = ReleaseFactory.build(
            version="0.0.0",
            project=ProjectFactory.build(name="test_project"),
            created=datetime.datetime(2017, 2, 5, 0, 0, 0, 0),
            yanked_reason="Yanky Doodle went to town",
        )

        result = email.send_yanked_project_release_email(
            db_request,
            [user, submitter_user],
            release=release,
            submitter_name=submitter_user.username,
            submitter_role="Owner",
            recipient_role="Owner",
        )

        assert result == {
            "project": release.project.name,
            "release": release.version,
            "release_date": release.created.strftime("%Y-%m-%d"),
            "submitter": submitter_user.username,
            "submitter_role": "owner",
            "recipient_role_descr": "an owner",
            "yanked_reason": "Yanky Doodle went to town",
        }

        subject_renderer.assert_(project="test_project")
        subject_renderer.assert_(release="0.0.0")
        body_renderer.assert_(project="test_project")
        body_renderer.assert_(release="0.0.0")
        body_renderer.assert_(release_date=release.created.strftime("%Y-%m-%d"))
        body_renderer.assert_(submitter=submitter_user.username)
        body_renderer.assert_(submitter_role="owner")
        body_renderer.assert_(recipient_role_descr="an owner")

        assert db_request.task.call_args_list == [
            mocker.call(send_email),
            mocker.call(send_email),
        ]

        assert send_email.delay.call_args_list == [
            mocker.call(
                "username <email@example.com>",
                {
                    "sender": None,
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "email@example.com",
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
            mocker.call(
                "submitterusername <submiteremail@example.com>",
                {
                    "sender": None,
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
        self, db_request, make_email_renderers, send_email, mocker
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        submitter_user = EmailFactory.create(
            email="submiteremail@example.com",
            verified=True,
            user__username="submitterusername",
            user__name="",
        ).user

        subject_renderer, body_renderer, _html_renderer = make_email_renderers(
            "unyanked-project-release"
        )

        db_request.user = submitter_user

        release = ReleaseFactory.build(
            version="0.0.0",
            project=ProjectFactory.build(name="test_project"),
            created=datetime.datetime(2017, 2, 5, 0, 0, 0, 0),
            yanked_reason="",
        )

        result = email.send_unyanked_project_release_email(
            db_request,
            [user, submitter_user],
            release=release,
            submitter_name=submitter_user.username,
            submitter_role="Owner",
            recipient_role="Maintainer",
        )

        assert result == {
            "project": release.project.name,
            "release": release.version,
            "release_date": release.created.strftime("%Y-%m-%d"),
            "submitter": submitter_user.username,
            "submitter_role": "owner",
            "recipient_role_descr": "a maintainer",
        }

        subject_renderer.assert_(project="test_project")
        subject_renderer.assert_(release="0.0.0")
        body_renderer.assert_(project="test_project")
        body_renderer.assert_(release="0.0.0")
        body_renderer.assert_(release_date=release.created.strftime("%Y-%m-%d"))
        body_renderer.assert_(submitter=submitter_user.username)
        body_renderer.assert_(submitter_role="owner")
        body_renderer.assert_(recipient_role_descr="a maintainer")

        assert db_request.task.call_args_list == [
            mocker.call(send_email),
            mocker.call(send_email),
        ]

        assert send_email.delay.call_args_list == [
            mocker.call(
                "username <email@example.com>",
                {
                    "sender": None,
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "email@example.com",
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
            mocker.call(
                "submitterusername <submiteremail@example.com>",
                {
                    "sender": None,
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
                        "from_": "noreply@example.com",
                        "to": "submiteremail@example.com",
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            ),
        ]

    def test_send_unyanked_project_release_email_to_owner(
        self, db_request, make_email_renderers, send_email, mocker
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        submitter_user = EmailFactory.create(
            email="submiteremail@example.com",
            verified=True,
            user__username="submitterusername",
            user__name="",
        ).user

        subject_renderer, body_renderer, _html_renderer = make_email_renderers(
            "unyanked-project-release"
        )

        db_request.user = submitter_user

        release = ReleaseFactory.build(
            version="0.0.0",
            project=ProjectFactory.build(name="test_project"),
            created=datetime.datetime(2017, 2, 5, 0, 0, 0, 0),
            yanked_reason="",
        )

        result = email.send_unyanked_project_release_email(
            db_request,
            [user, submitter_user],
            release=release,
            submitter_name=submitter_user.username,
            submitter_role="Owner",
            recipient_role="Owner",
        )

        assert result == {
            "project": release.project.name,
            "release": release.version,
            "release_date": release.created.strftime("%Y-%m-%d"),
            "submitter": submitter_user.username,
            "submitter_role": "owner",
            "recipient_role_descr": "an owner",
        }

        subject_renderer.assert_(project="test_project")
        subject_renderer.assert_(release="0.0.0")
        body_renderer.assert_(project="test_project")
        body_renderer.assert_(release="0.0.0")
        body_renderer.assert_(release_date=release.created.strftime("%Y-%m-%d"))
        body_renderer.assert_(submitter=submitter_user.username)
        body_renderer.assert_(submitter_role="owner")
        body_renderer.assert_(recipient_role_descr="an owner")

        assert db_request.task.call_args_list == [
            mocker.call(send_email),
            mocker.call(send_email),
        ]

        assert send_email.delay.call_args_list == [
            mocker.call(
                "username <email@example.com>",
                {
                    "sender": None,
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "email@example.com",
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
            mocker.call(
                "submitterusername <submiteremail@example.com>",
                {
                    "sender": None,
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
        self, db_request, make_email_renderers, send_email, mocker
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        submitter_user = EmailFactory.create(
            email="submiteremail@example.com",
            verified=True,
            user__username="submitterusername",
            user__name="",
        ).user

        subject_renderer, body_renderer, _html_renderer = make_email_renderers(
            "removed-project-release"
        )

        db_request.user = submitter_user

        release = ReleaseFactory.build(
            version="0.0.0",
            project=ProjectFactory.build(name="test_project"),
            created=datetime.datetime(2017, 2, 5, 0, 0, 0, 0),
            yanked_reason="",
        )

        result = email.send_removed_project_release_email(
            db_request,
            [user, submitter_user],
            release=release,
            submitter_name=submitter_user.username,
            submitter_role="Owner",
            recipient_role="Maintainer",
        )

        assert result == {
            "project_name": release.project.name,
            "release_version": release.version,
            "release_date": release.created.strftime("%Y-%m-%d"),
            "submitter_name": submitter_user.username,
            "submitter_role": "owner",
            "recipient_role_descr": "a maintainer",
            "reason": None,
        }

        subject_renderer.assert_(project_name="test_project")
        subject_renderer.assert_(release_version="0.0.0")
        body_renderer.assert_(project_name="test_project")
        body_renderer.assert_(release_version="0.0.0")
        body_renderer.assert_(release_date=release.created.strftime("%Y-%m-%d"))
        body_renderer.assert_(submitter_name=submitter_user.username)
        body_renderer.assert_(submitter_role="owner")
        body_renderer.assert_(recipient_role_descr="a maintainer")

        assert db_request.task.call_args_list == [
            mocker.call(send_email),
            mocker.call(send_email),
        ]

        assert send_email.delay.call_args_list == [
            mocker.call(
                "username <email@example.com>",
                {
                    "sender": None,
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "email@example.com",
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
            mocker.call(
                "submitterusername <submiteremail@example.com>",
                {
                    "sender": None,
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
                        "from_": "noreply@example.com",
                        "to": "submiteremail@example.com",
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            ),
        ]

    def test_send_removed_project_release_email_to_owner(
        self, db_request, make_email_renderers, send_email, mocker
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        submitter_user = EmailFactory.create(
            email="submiteremail@example.com",
            verified=True,
            user__username="submitterusername",
            user__name="",
        ).user

        subject_renderer, body_renderer, _html_renderer = make_email_renderers(
            "removed-project-release"
        )

        db_request.user = submitter_user

        release = ReleaseFactory.build(
            version="0.0.0",
            project=ProjectFactory.build(name="test_project"),
            created=datetime.datetime(2017, 2, 5, 0, 0, 0, 0),
            yanked_reason="",
        )

        result = email.send_removed_project_release_email(
            db_request,
            [user, submitter_user],
            release=release,
            submitter_name=submitter_user.username,
            submitter_role="Owner",
            recipient_role="Owner",
        )

        assert result == {
            "project_name": release.project.name,
            "release_version": release.version,
            "release_date": release.created.strftime("%Y-%m-%d"),
            "submitter_name": submitter_user.username,
            "submitter_role": "owner",
            "recipient_role_descr": "an owner",
            "reason": None,
        }

        subject_renderer.assert_(project_name="test_project")
        subject_renderer.assert_(release_version="0.0.0")
        body_renderer.assert_(project_name="test_project")
        body_renderer.assert_(release_version="0.0.0")
        body_renderer.assert_(release_date=release.created.strftime("%Y-%m-%d"))
        body_renderer.assert_(submitter_name=submitter_user.username)
        body_renderer.assert_(submitter_role="owner")
        body_renderer.assert_(recipient_role_descr="an owner")

        assert db_request.task.call_args_list == [
            mocker.call(send_email),
            mocker.call(send_email),
        ]

        assert send_email.delay.call_args_list == [
            mocker.call(
                "username <email@example.com>",
                {
                    "sender": None,
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "email@example.com",
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
            mocker.call(
                "submitterusername <submiteremail@example.com>",
                {
                    "sender": None,
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
        self, db_request, make_email_renderers, send_email, mocker
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        submitter_user = EmailFactory.create(
            email="submiteremail@example.com",
            verified=True,
            user__username="submitterusername",
            user__name="",
        ).user

        subject_renderer, body_renderer, _html_renderer = make_email_renderers(
            "removed-project-release-file"
        )

        db_request.user = submitter_user

        release = ReleaseFactory.build(
            version="0.0.0",
            project=ProjectFactory.build(name="test_project"),
            created=datetime.datetime(2017, 2, 5, 0, 0, 0, 0),
            yanked_reason="",
        )

        result = email.send_removed_project_release_file_email(
            db_request,
            [user, submitter_user],
            file="test-file-0.0.0.tar.gz",
            release=release,
            submitter_name=submitter_user.username,
            submitter_role="Owner",
            recipient_role="Owner",
        )

        assert result == {
            "file": "test-file-0.0.0.tar.gz",
            "project_name": release.project.name,
            "release_version": release.version,
            "submitter_name": submitter_user.username,
            "submitter_role": "owner",
            "recipient_role_descr": "an owner",
            "reason": None,
        }

        subject_renderer.assert_(project_name="test_project")
        subject_renderer.assert_(release_version="0.0.0")
        body_renderer.assert_(file="test-file-0.0.0.tar.gz")
        body_renderer.assert_(release_version="0.0.0")
        body_renderer.assert_(project_name="test_project")
        body_renderer.assert_(submitter_name=submitter_user.username)
        body_renderer.assert_(submitter_role="owner")
        body_renderer.assert_(recipient_role_descr="an owner")

        assert db_request.task.call_args_list == [
            mocker.call(send_email),
            mocker.call(send_email),
        ]

        assert send_email.delay.call_args_list == [
            mocker.call(
                "username <email@example.com>",
                {
                    "sender": None,
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "email@example.com",
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
            mocker.call(
                "submitterusername <submiteremail@example.com>",
                {
                    "sender": None,
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
                        "from_": "noreply@example.com",
                        "to": "submiteremail@example.com",
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            ),
        ]

    def test_send_removed_project_release_file_email_to_maintainer(
        self, db_request, make_email_renderers, send_email, mocker
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        submitter_user = EmailFactory.create(
            email="submiteremail@example.com",
            verified=True,
            user__username="submitterusername",
            user__name="",
        ).user

        subject_renderer, body_renderer, _html_renderer = make_email_renderers(
            "removed-project-release-file"
        )

        db_request.user = submitter_user

        release = ReleaseFactory.build(
            version="0.0.0",
            project=ProjectFactory.build(name="test_project"),
            created=datetime.datetime(2017, 2, 5, 0, 0, 0, 0),
            yanked_reason="",
        )

        result = email.send_removed_project_release_file_email(
            db_request,
            [user, submitter_user],
            file="test-file-0.0.0.tar.gz",
            release=release,
            submitter_name=submitter_user.username,
            submitter_role="Owner",
            recipient_role="Maintainer",
        )

        assert result == {
            "file": "test-file-0.0.0.tar.gz",
            "project_name": release.project.name,
            "release_version": release.version,
            "submitter_name": submitter_user.username,
            "submitter_role": "owner",
            "recipient_role_descr": "a maintainer",
            "reason": None,
        }

        subject_renderer.assert_(project_name="test_project")
        subject_renderer.assert_(release_version="0.0.0")
        body_renderer.assert_(file="test-file-0.0.0.tar.gz")
        body_renderer.assert_(release_version="0.0.0")
        body_renderer.assert_(project_name="test_project")
        body_renderer.assert_(submitter_name=submitter_user.username)
        body_renderer.assert_(submitter_role="owner")
        body_renderer.assert_(recipient_role_descr="a maintainer")

        assert db_request.task.call_args_list == [
            mocker.call(send_email),
            mocker.call(send_email),
        ]

        assert send_email.delay.call_args_list == [
            mocker.call(
                "username <email@example.com>",
                {
                    "sender": None,
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": "email@example.com",
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
            mocker.call(
                "submitterusername <submiteremail@example.com>",
                {
                    "sender": None,
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
        db_request,
        action,
        method,
        pretty_method,
        send_email,
        make_email_renderers,
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            f"two-factor-{action}"
        )

        db_request.user = user

        send_method = getattr(email, f"send_two_factor_{action}_email")
        result = send_method(db_request, user, method=method)

        assert result == {"method": pretty_method, "username": user.username}
        subject_renderer.assert_()
        body_renderer.assert_(method=pretty_method, username=user.username)
        html_renderer.assert_(method=pretty_method, username=user.username)
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{user.username} <{user.email}>",
            {
                "sender": None,
                "subject": "Email Subject",
                "body_text": "Email Body",
                "body_html": (
                    "<html>\n<head></head>\n"
                    "<body><p>Email HTML Body</p></body>\n</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": user.email,
                    "subject": "Email Subject",
                    "redact_ip": False,
                },
            },
        )


class TestRecoveryCodeEmails:
    @pytest.mark.parametrize(
        ("fn", "template_name"),
        [
            (email.send_recovery_codes_generated_email, "recovery-codes-generated"),
            (email.send_recovery_code_used_email, "recovery-code-used"),
            (email.send_recovery_code_reminder_email, "recovery-code-reminder"),
        ],
    )
    def test_recovery_code_emails(
        self, db_request, fn, template_name, send_email, make_email_renderers
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            template_name
        )

        db_request.user = user

        result = fn(db_request, user)

        assert result == {"username": user.username}
        subject_renderer.assert_()
        body_renderer.assert_(username=user.username)
        html_renderer.assert_(username=user.username)
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{user.username} <{user.email}>",
            {
                "sender": None,
                "subject": "Email Subject",
                "body_text": "Email Body",
                "body_html": (
                    "<html>\n<head></head>\n"
                    "<body><p>Email HTML Body</p></body>\n</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": user.email,
                    "subject": "Email Subject",
                    "redact_ip": False,
                },
            },
        )


class TestTrustedPublisherEmails:
    def test_pending_trusted_publisher_expired_email(
        self, db_request, make_email_renderers
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "pending-trusted-publisher-expired"
        )

        db_request.user = user

        result = email.send_pending_trusted_publisher_expired_email(
            db_request,
            user,
            project_name="test_project",
            days=30,
        )

        assert result == {
            "project_name": "test_project",
            "days": 30,
        }
        subject_renderer.assert_()
        body_renderer.assert_(project_name="test_project", days=30)
        html_renderer.assert_(project_name="test_project", days=30)

    def test_pending_trusted_publisher_expiration_reminder_email(
        self, db_request, make_email_renderers
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "pending-trusted-publisher-expiration-reminder"
        )

        db_request.user = user

        result = email.send_pending_trusted_publisher_expiration_reminder_email(
            db_request,
            user,
            project_name="test_project",
            days_remaining=5,
        )

        assert result == {
            "project_name": "test_project",
            "days_remaining": 5,
        }
        subject_renderer.assert_()
        body_renderer.assert_(project_name="test_project", days_remaining=5)
        html_renderer.assert_(project_name="test_project", days_remaining=5)

    def test_pending_trusted_publisher_reified_email(
        self, db_request, make_email_renderers
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "pending-trusted-publisher-reified"
        )

        db_request.user = user

        result = email.send_pending_trusted_publisher_reified_email(
            db_request,
            user,
            project_name="test_project",
            publisher_specifier="foo/bar via release.yml",
        )

        assert result == {
            "project_name": "test_project",
            "publisher_specifier": "foo/bar via release.yml",
        }
        subject_renderer.assert_()
        body_renderer.assert_(
            project_name="test_project",
            publisher_specifier="foo/bar via release.yml",
        )
        html_renderer.assert_(
            project_name="test_project",
            publisher_specifier="foo/bar via release.yml",
        )

    @pytest.mark.parametrize(
        ("fn", "template_name"),
        [
            (
                email.send_pending_trusted_publisher_invalidated_email,
                "pending-trusted-publisher-invalidated",
            ),
        ],
    )
    def test_pending_trusted_publisher_emails(
        self, db_request, fn, template_name, send_email, make_email_renderers
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            template_name
        )

        db_request.user = user

        project_name = "test_project"
        result = fn(
            db_request,
            user,
            project_name=project_name,
        )

        assert result == {
            "project_name": project_name,
        }
        subject_renderer.assert_()
        body_renderer.assert_(project_name=project_name)
        html_renderer.assert_(project_name=project_name)
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{user.username} <{user.email}>",
            {
                "sender": None,
                "subject": "Email Subject",
                "body_text": "Email Body",
                "body_html": (
                    "<html>\n<head></head>\n"
                    "<body><p>Email HTML Body</p></body>\n</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": user.email,
                    "subject": "Email Subject",
                    "redact_ip": False,
                },
            },
        )

    @pytest.mark.parametrize(
        ("fn", "template_name"),
        [
            (email.send_trusted_publisher_added_email, "trusted-publisher-added"),
            (email.send_trusted_publisher_removed_email, "trusted-publisher-removed"),
        ],
    )
    def test_trusted_publisher_emails(
        self, db_request, fn, template_name, send_email, make_email_renderers
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            template_name
        )

        db_request.user = user

        project_name = "test_project"
        fakepublisher = GitHubPublisherFactory.build(
            repository_owner="fakeowner",
            repository_name="fakerepository",
            environment="fakeenvironment",
        )

        result = fn(
            db_request,
            user,
            project_name=project_name,
            publisher=fakepublisher,
        )

        assert result == {
            "username": user.username,
            "project_name": project_name,
            "publisher": fakepublisher,
        }
        subject_renderer.assert_()
        body_renderer.assert_(username=user.username, project_name=project_name)
        html_renderer.assert_(username=user.username, project_name=project_name)
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{user.username} <{user.email}>",
            {
                "sender": None,
                "subject": "Email Subject",
                "body_text": "Email Body",
                "body_html": (
                    "<html>\n<head></head>\n"
                    "<body><p>Email HTML Body</p></body>\n</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": user.email,
                    "subject": "Email Subject",
                    "redact_ip": False,
                },
            },
        )

    def test_api_token_warning_with_trusted_publisher_emails(
        self, db_request, send_email, mocker, make_email_renderers
    ):
        template_name = "api-token-used-in-trusted-publisher-project"
        # We set up two users to receive the email. The owner of the API token
        # will be user, their username should be the one mentioned in the
        # email body.
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        maintainer_user = EmailFactory.create(
            email="email_maintainer@example.com",
            verified=True,
            user__username="username_maintainer",
            user__name="",
        ).user
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            template_name
        )

        db_request.user = user

        project_name = "test_project"
        api_token_name = "old_api_token"
        result = email.send_api_token_used_in_trusted_publisher_project_email(
            db_request,
            [user, maintainer_user],
            project_name=project_name,
            token_owner_username=user.username,
            token_name=api_token_name,
        )

        assert result == {
            "project_name": project_name,
            "token_owner_username": user.username,
            "token_name": api_token_name,
        }
        subject_renderer.assert_()
        body_renderer.assert_(
            project_name=project_name,
            token_owner_username=user.username,
            token_name=api_token_name,
        )
        html_renderer.assert_(
            project_name=project_name,
            token_owner_username=user.username,
            token_name=api_token_name,
        )
        assert db_request.task.call_args_list == [
            mocker.call(send_email),
            mocker.call(send_email),
        ]
        assert send_email.delay.call_args_list == [
            mocker.call(
                f"{user.username} <{user.email}>",
                {
                    "sender": None,
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": user.email,
                        "subject": "Email Subject",
                        "redact_ip": False,
                    },
                },
            ),
            mocker.call(
                f"{maintainer_user.username} <{maintainer_user.email}>",
                {
                    "sender": None,
                    "subject": "Email Subject",
                    "body_text": "Email Body",
                    "body_html": (
                        "<html>\n<head></head>\n"
                        "<body><p>Email HTML Body</p></body>\n</html>\n"
                    ),
                },
                {
                    "tag": "account:email:sent",
                    "user_id": maintainer_user.id,
                    "additional": {
                        "from_": "noreply@example.com",
                        "to": maintainer_user.email,
                        "subject": "Email Subject",
                        "redact_ip": True,
                    },
                },
            ),
        ]

    def test_environment_ignored_in_trusted_publisher_emails(
        self, db_request, send_email, make_email_renderers
    ):
        template_name = "environment-ignored-in-trusted-publisher"
        owner_user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username_owner",
            user__name="",
        ).user
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            template_name
        )

        fakepublisher = GitHubPublisherFactory.build(
            repository_owner="fakeowner",
            repository_name="fakerepository",
            environment="",
        )
        fakeenvironment = "fakeenvironment"
        db_request.user = owner_user

        project_name = "test_project"
        result = email.send_environment_ignored_in_trusted_publisher_email(
            db_request,
            [owner_user],
            project_name=project_name,
            publisher=fakepublisher,
            environment_name=fakeenvironment,
        )

        assert result == {
            "project_name": project_name,
            "publisher": fakepublisher,
            "environment_name": fakeenvironment,
        }
        subject_renderer.assert_()
        body_renderer.assert_()
        html_renderer.assert_(
            project_name=project_name,
            publisher=fakepublisher,
            environment_name=fakeenvironment,
        )
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{owner_user.username} <{owner_user.email}>",
            {
                "sender": None,
                "subject": "Email Subject",
                "body_text": "Email Body",
                "body_html": (
                    "<html>\n<head></head>\n"
                    "<body><p>Email HTML Body</p></body>\n</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": owner_user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": owner_user.email,
                    "subject": "Email Subject",
                    "redact_ip": False,
                },
            },
        )

    def test_wheel_record_mismatch_email(
        self, db_request, make_email_renderers, send_email
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "wheel-record-mismatch-email"
        )

        db_request.user = user

        project_name = "Test_Project"
        filename = "Test_Project-1.0-py3-none-any.whl"

        result = email.send_wheel_record_mismatch_email(
            db_request,
            {user},
            project_name=project_name,
            filename=filename,
        )

        assert result == {
            "project_name": project_name,
            "filename": filename,
        }
        subject_renderer.assert_(project_name=project_name)
        body_renderer.assert_(project_name=project_name)
        html_renderer.assert_(project_name=project_name)

        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{user.username} <{user.email}>",
            {
                "sender": None,
                "subject": "Email Subject",
                "body_text": "Email Body",
                "body_html": (
                    "<html>\n<head></head>\n"
                    "<body><p>Email HTML Body</p></body>\n</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": user.email,
                    "subject": "Email Subject",
                    "redact_ip": False,
                },
            },
        )


class TestUserTermsOfServiceUpdateEmail:
    def test_user_terms_of_service_updated(
        self, db_request, make_email_renderers, send_email
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "user-terms-of-service-updated"
        )

        db_request.user = user

        send_method = email.send_user_terms_of_service_updated
        result = send_method(db_request, user)

        assert result == {"user": user}
        subject_renderer.assert_()
        body_renderer.assert_(user=user)
        html_renderer.assert_(user=user)
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{user.username} <{user.email}>",
            {
                "sender": None,
                "subject": "Email Subject",
                "body_text": "Email Body",
                "body_html": (
                    "<html>\n<head></head>\n"
                    "<body><p>Email HTML Body</p></body>\n</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": user.email,
                    "subject": "Email Subject",
                    "redact_ip": False,
                },
            },
        )


class TestSendUnrecognizedLoginEmail:
    def test_send_unrecognized_login_email(
        self, db_request, make_email_renderers, send_email
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        ip_address = "127.0.0.1"
        user_agent = "Test Browser"
        token = "test-token"

        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "unrecognized-login"
        )

        db_request.user = user

        result = email.send_unrecognized_login_email(
            db_request,
            user,
            ip_address=ip_address,
            user_agent=user_agent,
            token=token,
        )

        assert result == {
            "username": user.username,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "token": token,
        }
        subject_renderer.assert_()
        body_renderer.assert_(
            username=user.username,
            ip_address=ip_address,
            user_agent=user_agent,
            token=token,
        )
        html_renderer.assert_(
            username=user.username,
            ip_address=ip_address,
            user_agent=user_agent,
            token=token,
        )
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{user.username} <{user.email}>",
            {
                "sender": None,
                "subject": "Email Subject",
                "body_text": "Email Body",
                "body_html": (
                    "<html>\n<head></head>\n"
                    "<body><p>Email HTML Body</p></body>\n</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": user.email,
                    "subject": "Email Subject",
                    "redact_ip": False,
                },
            },
        )

    def test_send_unrecognized_login_email_throttled_within_repeat_window(
        self,
        pyramid_request,
        metrics,
        email_service,
        send_email,
        make_email_renderers,
        mocker,
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        make_email_renderers("unrecognized-login")

        # The same email went out moments ago, e.g. on a previous login attempt
        last_sent = mocker.patch.object(
            email_service,
            "last_sent",
            autospec=True,
            return_value=datetime.datetime.now() - datetime.timedelta(minutes=1),
        )

        email.send_unrecognized_login_email(
            pyramid_request,
            user,
            ip_address="127.0.0.1",
            user_agent="Test Browser",
            token="test-token",
        )

        last_sent.assert_called_once_with(to=user.email, subject="Email Subject")
        pyramid_request.task.assert_not_called()
        send_email.delay.assert_not_called()
        metrics.increment.assert_called_once_with(
            "warehouse.emails.skipped",
            tags=[
                "template_name:unrecognized-login",
                "allow_unverified:True",
                "repeat_window:900.0",
                "reason:repeat-window",
            ],
        )

    def test_send_unrecognized_login_email_repeat_window_override(
        self,
        db_request,
        metrics,
        email_service,
        send_email,
        make_email_renderers,
        mocker,
    ):
        """A per-call repeat_window of None bypasses the decorator's throttle."""
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        make_email_renderers("unrecognized-login")

        # The same email went out moments ago, e.g. for a different device
        last_sent = mocker.patch.object(
            email_service,
            "last_sent",
            autospec=True,
            return_value=datetime.datetime.now() - datetime.timedelta(minutes=1),
        )

        db_request.user = user

        email.send_unrecognized_login_email(
            db_request,
            user,
            ip_address="127.0.0.1",
            user_agent="Test Browser",
            token="test-token",
            repeat_window=None,
        )

        # The throttle was never consulted and the email was scheduled
        last_sent.assert_not_called()
        db_request.task.assert_called_once_with(send_email)
        assert send_email.delay.call_count == 1
        metrics.increment.assert_called_once_with(
            "warehouse.emails.scheduled",
            tags=[
                "template_name:unrecognized-login",
                "allow_unverified:True",
                "repeat_window:none",
            ],
        )


class TestAccountAssociationAddedEmail:
    def test_send_account_association_added_email(
        self, db_request, make_email_renderers, send_email
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "account-association-added"
        )

        db_request.user = user

        result = email.send_account_association_added_email(
            db_request,
            user,
            service="GitHub",
            external_username="testuser",
        )

        assert result == {
            "username": user.username,
            "service": "GitHub",
            "external_username": "testuser",
        }
        subject_renderer.assert_()
        body_renderer.assert_(
            username=user.username,
            service="GitHub",
            external_username="testuser",
        )
        html_renderer.assert_(
            username=user.username,
            service="GitHub",
            external_username="testuser",
        )
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{user.username} <{user.email}>",
            {
                "sender": None,
                "subject": "Email Subject",
                "body_text": "Email Body",
                "body_html": (
                    "<html>\n<head></head>\n"
                    "<body><p>Email HTML Body</p></body>\n</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": user.email,
                    "subject": "Email Subject",
                    "redact_ip": False,
                },
            },
        )

    def test_send_account_association_added_email_unverified(
        self, db_request, send_email, make_email_renderers
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=False,
            user__username="username",
            user__name="",
        ).user
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "account-association-added", html="Email HTML Body"
        )

        db_request.user = user

        result = email.send_account_association_added_email(
            db_request,
            user,
            service="GitHub",
            external_username="testuser",
        )

        assert result == {
            "username": user.username,
            "service": "GitHub",
            "external_username": "testuser",
        }
        subject_renderer.assert_()
        body_renderer.assert_(
            username=user.username,
            service="GitHub",
            external_username="testuser",
        )
        html_renderer.assert_(
            username=user.username,
            service="GitHub",
            external_username="testuser",
        )
        # Email should not be sent for unverified email
        db_request.task.assert_not_called()
        send_email.delay.assert_not_called()


class TestAccountAssociationRemovedEmail:
    def test_send_account_association_removed_email(
        self, db_request, make_email_renderers, send_email
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=True,
            user__username="username",
            user__name="",
        ).user
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "account-association-removed"
        )

        db_request.user = user

        result = email.send_account_association_removed_email(
            db_request,
            user,
            service="GitHub",
            external_username="testuser",
        )

        assert result == {
            "username": user.username,
            "service": "GitHub",
            "external_username": "testuser",
        }
        subject_renderer.assert_()
        body_renderer.assert_(
            username=user.username,
            service="GitHub",
            external_username="testuser",
        )
        html_renderer.assert_(
            username=user.username,
            service="GitHub",
            external_username="testuser",
        )
        db_request.task.assert_called_once_with(send_email)
        send_email.delay.assert_called_once_with(
            f"{user.username} <{user.email}>",
            {
                "sender": None,
                "subject": "Email Subject",
                "body_text": "Email Body",
                "body_html": (
                    "<html>\n<head></head>\n"
                    "<body><p>Email HTML Body</p></body>\n</html>\n"
                ),
            },
            {
                "tag": "account:email:sent",
                "user_id": user.id,
                "additional": {
                    "from_": "noreply@example.com",
                    "to": user.email,
                    "subject": "Email Subject",
                    "redact_ip": False,
                },
            },
        )

    def test_send_account_association_removed_email_unverified(
        self, db_request, send_email, make_email_renderers
    ):
        user = EmailFactory.create(
            email="email@example.com",
            verified=False,
            user__username="username",
            user__name="",
        ).user
        subject_renderer, body_renderer, html_renderer = make_email_renderers(
            "account-association-removed", html="Email HTML Body"
        )

        db_request.user = user

        result = email.send_account_association_removed_email(
            db_request,
            user,
            service="GitHub",
            external_username="testuser",
        )

        assert result == {
            "username": user.username,
            "service": "GitHub",
            "external_username": "testuser",
        }
        subject_renderer.assert_()
        body_renderer.assert_(
            username=user.username,
            service="GitHub",
            external_username="testuser",
        )
        html_renderer.assert_(
            username=user.username,
            service="GitHub",
            external_username="testuser",
        )
        # Email should not be sent for unverified email
        db_request.task.assert_not_called()
        send_email.delay.assert_not_called()
