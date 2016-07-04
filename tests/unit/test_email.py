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
import requests

from unittest import mock
from pyramid_mailer.interfaces import IMailer
from pyramid_mailer.message import Message
from zope.interface.verify import verifyClass

from warehouse import email


class TestSendEmail:

    def test_send_email_success(self):
        task = pretend.stub()
        mailer = pretend.stub(
            send_immediately=pretend.call_recorder(lambda i: None)
        )
        request = pretend.stub(
            registry = pretend.stub(
                settings=pretend.stub(
                    get=pretend.call_recorder(lambda k: 'SENDER'),
                ),
                getUtility=pretend.call_recorder(lambda mailr: mailer)
            )
        )

        email.send_email.__wrapped__.__func__(
            task, request, "body", ["recipients"], "subject"
        )

        assert len(mailer.send_immediately.calls) == 1
        assert request.registry.getUtility.calls == [pretend.call(IMailer)]
        assert request.registry.settings.get.calls  == [pretend.call("mail.sender")]

    def test_send_email_failure(self):
        exc = Exception()

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

        mailer, task = Mailer(), Task()
        request = pretend.stub(
            registry = pretend.stub(
                settings=pretend.stub(
                    get=pretend.call_recorder(lambda k: 'SENDER'),
                ),
                getUtility=pretend.call_recorder(lambda mailr: mailer)
            )
        )

        with pytest.raises(celery.exceptions.Retry):
            email.send_email.__wrapped__.__func__(
                task, request, "body", ["recipients"], "subject"
            )

        assert len(mailer.send_immediately.calls) == 1
        assert request.registry.getUtility.calls == [pretend.call(IMailer)]
        assert request.registry.settings.get.calls  == [
            pretend.call("mail.sender")]
        assert task.retry.calls  == [pretend.call(exc=exc)]
