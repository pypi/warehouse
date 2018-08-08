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

from typing import Optional

import attr

from jinja2.exceptions import TemplateNotFound
from pyramid.renderers import render
from zope.interface import Interface


@attr.s(auto_attribs=True, frozen=True, slots=True)
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
        # Catching TemplateNotFound here is a bit of a leaky abstraction, but there's
        # not much we can do about it.
        except TemplateNotFound:
            body_html = None

        return cls(subject=subject, body_text=body_text, body_html=body_html)


class IEmailSender(Interface):
    def create_service(context, request):
        """
        Create the service, given the context and request for which it is being
        created for.
        """

    def send(recipient, message):
        """
        Sends an EmailMessage to the given recipient.
        """
