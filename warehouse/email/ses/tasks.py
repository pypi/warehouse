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

import datetime

from warehouse import tasks
from warehouse.email.ses.models import EmailMessage

CLEANUP_DELIVERED_AFTER = datetime.timedelta(days=14)

CLEANUP_AFTER = datetime.timedelta(days=90)


@tasks.task(ignore_result=True, acks_late=True)
def cleanup(request):
    # Cleanup any email message whose status is Accepted or Delivered.
    # We clean these up quicker than failures because we don't really
    # need them, and this limits the amount of data stored in the
    # database.
    (
        request.db.query(EmailMessage)
        .filter(EmailMessage.status.in_(["Accepted", "Delivered"]))
        .filter(
            EmailMessage.created
            < (datetime.datetime.now(datetime.UTC) - CLEANUP_DELIVERED_AFTER)
        )
        .delete(synchronize_session=False)
    )

    # Cleanup *all* messages, this is our hard limit after which we
    # will not continue to save the email message data.
    (
        request.db.query(EmailMessage)
        .filter(
            EmailMessage.created < (datetime.datetime.now(datetime.UTC) - CLEANUP_AFTER)
        )
        .delete(synchronize_session=False)
    )
