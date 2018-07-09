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

from email.headerregistry import Address
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr, formataddr

from pyramid_mailer import get_mailer
from pyramid_mailer.message import Message
from zope.interface import implementer

from warehouse.email.interfaces import IEmailSender
from warehouse.email.ses.models import EmailMessage


def _format_sender(sitename, sender):
    if sender is not None:
        return str(Address(sitename, addr_spec=sender))


@implementer(IEmailSender)
class SMTPEmailSender:
    def __init__(self, mailer, sender=None):
        self.mailer = mailer
        self.sender = sender

    @classmethod
    def create_service(cls, context, request):
        sitename = request.registry.settings["site.name"]
        sender = _format_sender(sitename, request.registry.settings.get("mail.sender"))
        return cls(get_mailer(request), sender=sender)

    def send(self, subject, body, *, recipient):
        message = Message(
            subject=subject, body=body, recipients=[recipient], sender=self.sender
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
        sitename = request.registry.settings["site.name"]
        sender = _format_sender(sitename, request.registry.settings.get("mail.sender"))

        aws_session = request.find_service(name="aws.session")

        return cls(
            aws_session.client(
                "ses", region_name=request.registry.settings.get("mail.region")
            ),
            sender=sender,
            db=request.db,
        )

    def send(self, subject, body, *, recipient):
        message = MIMEMultipart("mixed")
        message["Subject"] = subject
        message["From"] = self._sender

        # The following is necessary to support friendly names with Unicode characters,
        # otherwise the entire value will get encoded and will not be accepted by SES:
        #
        #   >>> parseaddr("Fööbar <foo@bar.com>")
        #   ('Fööbar', 'foo@bar.com')
        #   >>> formataddr(_)
        #   '=?utf-8?b?RsO2w7ZiYXI=?= <foo@bar.com>'
        message["To"] = formataddr(parseaddr(recipient))

        message.attach(MIMEText(body, "plain", "utf-8"))

        resp = self._client.send_raw_email(
            Source=self._sender,
            Destinations=[recipient],
            RawMessage={"Data": message.as_string()},
        )

        self._db.add(
            EmailMessage(
                message_id=resp["MessageId"],
                from_=parseaddr(self._sender)[1],
                to=parseaddr(recipient)[1],
                subject=subject,
            )
        )
