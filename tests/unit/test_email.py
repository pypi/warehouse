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

from pyramid_mailer.message import Message
from pyramid_mailer.interfaces import IMailer

from warehouse import email
from warehouse.accounts.interfaces import ITokenService


class TestSendEmail:

    def test_send_email_success(self, monkeypatch):
        message_obj = Message()

        def mock_message(*args, **kwargs):
            return message_obj

        monkeypatch.setattr(email, "Message", mock_message)

        task = pretend.stub()
        mailer = pretend.stub(
            send_immediately=pretend.call_recorder(lambda i: None)
        )
        request = pretend.stub(
            registry=pretend.stub(
                settings=pretend.stub(
                    get=pretend.call_recorder(lambda k: 'SENDER'),
                ),
                getUtility=pretend.call_recorder(lambda mailr: mailer)
            )
        )

        email.send_email(task, request, "body", ["recipients"], "subject")

        assert mailer.send_immediately.calls == [pretend.call(message_obj)]
        assert request.registry.getUtility.calls == [pretend.call(IMailer)]
        assert request.registry.settings.get.calls == [
            pretend.call("mail.sender")]

    def test_send_email_failure(self, monkeypatch):
        exc = Exception()
        message_obj = Message()

        class Mailer:
            @staticmethod
            @pretend.call_recorder
            def send_immediately(message):
                raise exc

        class Task:
            @staticmethod
            @pretend.call_recorder
            def retry(exc):
                raise celery.exceptions.Retry

        def mock_message(*args, **kwargs):
            return message_obj

        monkeypatch.setattr(email, "Message", mock_message)

        mailer, task = Mailer(), Task()
        request = pretend.stub(
            registry=pretend.stub(
                settings=pretend.stub(
                    get=pretend.call_recorder(lambda k: 'SENDER'),
                ),
                getUtility=pretend.call_recorder(lambda mailr: mailer)
            )
        )

        with pytest.raises(celery.exceptions.Retry):
            email.send_email(task, request, "body", ["recipients"], "subject")

        assert mailer.send_immediately.calls == [pretend.call(message_obj)]
        assert request.registry.getUtility.calls == [pretend.call(IMailer)]
        assert request.registry.settings.get.calls == [
            pretend.call("mail.sender")]
        assert task.retry.calls == [pretend.call(exc=exc)]


class TestSendPasswordResetEmail:

    def test_send_password_reset_email(
            self, pyramid_request, pyramid_config, token_service, monkeypatch):

        stub_user = pretend.stub(
            id='id',
            email='email',
            username='username_value',
            last_login='last_login',
            password_date='password_date',
        )
        pyramid_request.method = 'POST'
        token_service.dumps = pretend.call_recorder(lambda a: 'TOKEN')
        pyramid_request.find_service = pretend.call_recorder(
            lambda *a, **kw: token_service
        )

        subject_renderer = pyramid_config.testing_add_renderer(
            'email/password-reset.subject.txt'
        )
        subject_renderer.string_response = 'Email Subject'
        body_renderer = pyramid_config.testing_add_renderer(
            'email/password-reset.body.txt'
        )
        body_renderer.string_response = 'Email Body'

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(
            lambda *args, **kwargs: send_email
        )
        monkeypatch.setattr(email, 'send_email', send_email)

        result = email.send_password_reset_email(
            pyramid_request,
            user=stub_user,
        )

        assert result == {
            'token': 'TOKEN',
            'username': stub_user.username,
            'n_hours': token_service.max_age // 60 // 60,
        }
        subject_renderer.assert_()
        body_renderer.assert_(token='TOKEN', username=stub_user.username)
        assert token_service.dumps.calls == [
            pretend.call({
                'action': 'password-reset',
                'user.id': str(stub_user.id),
                'user.last_login': str(stub_user.last_login),
                'user.password_date': str(stub_user.password_date),
            }),
        ]
        assert pyramid_request.find_service.calls == [
            pretend.call(ITokenService, name='password'),
        ]
        assert pyramid_request.task.calls == [
            pretend.call(send_email),
        ]
        assert send_email.delay.calls == [
            pretend.call('Email Body', [stub_user.email], 'Email Subject'),
        ]


class TestEmailVerificationEmail:

    def test_email_verification_email(
            self, pyramid_request, pyramid_config, token_service, monkeypatch):

        stub_email = pretend.stub(
            id='id',
            email='email',
        )
        pyramid_request.method = 'POST'
        token_service.dumps = pretend.call_recorder(lambda a: 'TOKEN')
        pyramid_request.find_service = pretend.call_recorder(
            lambda *a, **kw: token_service
        )

        subject_renderer = pyramid_config.testing_add_renderer(
            'email/verify-email.subject.txt'
        )
        subject_renderer.string_response = 'Email Subject'
        body_renderer = pyramid_config.testing_add_renderer(
            'email/verify-email.body.txt'
        )
        body_renderer.string_response = 'Email Body'

        send_email = pretend.stub(
            delay=pretend.call_recorder(lambda *args, **kwargs: None)
        )
        pyramid_request.task = pretend.call_recorder(
            lambda *args, **kwargs: send_email
        )
        monkeypatch.setattr(email, 'send_email', send_email)

        result = email.send_email_verification_email(
            pyramid_request,
            email=stub_email,
        )

        assert result == {
            'token': 'TOKEN',
            'email_address': stub_email.email,
            'n_hours': token_service.max_age // 60 // 60,
        }
        subject_renderer.assert_()
        body_renderer.assert_(token='TOKEN', email_address=stub_email.email)
        assert token_service.dumps.calls == [
            pretend.call({
                'action': 'email-verify',
                'email.id': str(stub_email.id),
            }),
        ]
        assert pyramid_request.find_service.calls == [
            pretend.call(ITokenService, name='email'),
        ]
        assert pyramid_request.task.calls == [
            pretend.call(send_email),
        ]
        assert send_email.delay.calls == [
            pretend.call('Email Body', [stub_email.email], 'Email Subject'),
        ]
