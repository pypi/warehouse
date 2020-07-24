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
from email.message import EmailMessage as RawEmailMessage
from email.utils import parseaddr
from typing import Optional

import attr
import premailer

from jinja2.exceptions import TemplateNotFound
from pyramid.renderers import render
from pyramid_mailer import get_mailer
from pyramid_mailer.message import Message
from zope.interface import implementer

from warehouse.email.interfaces import IEmailSender
from warehouse.email.ses.models import EmailMessage as SESEmailMessage


def _format_sender(sitename, sender):
    if sender is not None:
        return str(Address(sitename, addr_spec=sender))



class EmailMessage:

    subject: str
    body_text: str
    body_html: Optional[str] = None

    @classmethod
    def from_template(cls, email_name, context, *, request):
        subject = render(f"email/{email_name}/subject.txt", context, request=request)
        body_text = render(f"email/{email_name}/body.txt", context, request=request)

        try:
            body_html = render(
                f"email/{email_name}/body.html", context, request=request
            )
            body_html = premailer.Premailer(body_html, remove_classes=True).transform()
        # Catching TemplateNotFound here is a bit of a leaky abstraction, but there's
        # not much we can do about it.
        except TemplateNotFound:
            body_html = None

        return cls(subject=subject, body_text=body_text, body_html=body_html)


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

    def send(self, recipient, message):
        self.mailer.send_immediately(
            Message(
                subject=message.subject,
                body=message.body_text,
                html=message.body_html,
                recipients=[recipient],
                sender=self.sender,
            )
        )


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

    def send(self, recipient, message):
        raw = RawEmailMessage()
        raw["Subject"] = message.subject
        raw["From"] = self._sender
        raw["To"] = recipient

        raw.set_content(message.body_text)
        if message.body_html:
            raw.add_alternative(message.body_html, subtype="html")

        resp = self._client.send_raw_email(
            Source=self._sender,
            Destinations=[recipient],
            RawMessage={"Data": bytes(raw)},
        )

        self._db.add(
            SESEmailMessage(
                message_id=resp["MessageId"],
                from_=parseaddr(self._sender)[1],
                to=parseaddr(recipient)[1],
                subject=message.subject,
            )
        )
