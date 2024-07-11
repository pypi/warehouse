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

from warehouse.email.ses.models import EmailMessage
from warehouse.email.ses.tasks import CLEANUP_AFTER, CLEANUP_DELIVERED_AFTER, cleanup

from ....common.db.ses import EmailMessageFactory


def test_cleanup_cleans_correctly(db_request):
    now = datetime.datetime.now(datetime.UTC)

    EmailMessageFactory.create(
        status="Delivered",
        created=(now - CLEANUP_DELIVERED_AFTER - datetime.timedelta(hours=1)),
    )
    EmailMessageFactory.create(
        status="Bounced", created=(now - CLEANUP_AFTER - datetime.timedelta(hours=1))
    )

    to_be_kept = [
        EmailMessageFactory.create(
            status="Delivered",
            created=(now - CLEANUP_DELIVERED_AFTER + datetime.timedelta(hours=1)),
        ),
        EmailMessageFactory.create(
            status="Bounced",
            created=(now - CLEANUP_AFTER + datetime.timedelta(hours=1)),
        ),
    ]

    cleanup(db_request)

    assert set(db_request.db.query(EmailMessage).all()) == set(to_be_kept)
