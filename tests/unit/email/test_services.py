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

import pretend

from pyramid_mailer.mailer import DummyMailer
from zope.interface.verify import verifyClass

from warehouse.email.interfaces import IEmailSender
from warehouse.email.services import SMTPEmailSender


class TestSMTPEmailSender:

    def test_verify_service(self):
        assert verifyClass(IEmailSender, SMTPEmailSender)

    def test_creates_service(self):
        mailer = pretend.stub()
        context = pretend.stub()
        request = pretend.stub(
            registry=pretend.stub(
                settings=pretend.stub(get=lambda k: "SENDER"),
                getUtility=lambda mailr: mailer,
            )
        )

        service = SMTPEmailSender.create_service(context, request)

        assert isinstance(service, SMTPEmailSender)
        assert service.mailer is mailer
        assert service.sender == "SENDER"

    def test_send(self):
        mailer = DummyMailer()
        service = SMTPEmailSender(mailer, sender="noreply@example.com")

        service.send("a subject", "a body", recipient="sombody@example.com")

        assert len(mailer.outbox) == 1

        msg = mailer.outbox[0]

        assert msg.subject == "a subject"
        assert msg.body == "a body"
        assert msg.recipients == ["sombody@example.com"]
        assert msg.sender == "noreply@example.com"
