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
from warehouse.email.ses.models import EmailMessage


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


@implementer(IEmailSender)
class SESEmailSender:

    def __init__(self, client, *, sender=None, db):
        self._client = client
        self._sender = sender
        self._db = db

    @classmethod
    def create_service(cls, context, request):
        aws_session = request.find_service(name="aws.session")
        return cls(
            aws_session.client(
                "ses",
                region_name=request.registry.settings.get("mail.region"),
            ),
            sender=request.registry.settings.get("mail.sender"),
            db=request.db,
        )

    def send(self, subject, body, *, recipient):
        resp = self._client.send_email(
            Source=self._sender,
            Destination={"ToAddresses": [recipient]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": body, "Charset": "UTF-8"},
                },
            },
        )

        self._db.add(
            EmailMessage(
                message_id=resp["MessageId"],
                from_=self._sender,
                to=recipient,
                subject=subject,
            ),
        )
