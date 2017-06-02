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

from warehouse import tasks


@tasks.task(bind=True, ignore_result=True, acks_late=True)
def send_email(task, request, body, recipients, subject):

    mailer = get_mailer(request)
    message = Message(
        body=body,
        recipients=recipients,
        sender=request.registry.settings.get('mail.sender'),
        subject=subject
    )
    try:
        mailer.send_immediately(message)
    except Exception as exc:
        task.retry(exc=exc)
