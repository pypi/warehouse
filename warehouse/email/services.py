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

from pyramid_mailer import get_mailer
from pyramid_mailer.message import Message
from zope.interface import implementer

from warehouse.email.interfaces import IEmailSender


@implementer(IEmailSender)
class SMTPEmailSender:

    def __init__(self, mailer, sender=None):
        self.mailer = mailer
        self.sender = sender

    @classmethod
    def create_service(cls, context, request):
        return cls(get_mailer(request),
                   sender=request.registry.settings.get("mail.sender"))

    def send(self, subject, body, *, recipient):
        message = Message(
            subject=subject,
            body=body,
            recipients=[recipient],
            sender=self.sender,
        )
        self.mailer.send_immediately(message)
