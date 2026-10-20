# SPDX-License-Identifier: Apache-2.0

import datetime as dt

from warehouse.email.ses.models import EmailMessage
from warehouse.email.ses.tasks import CLEANUP_AFTER, CLEANUP_DELIVERED_AFTER, cleanup

from ....common.db.ses import EmailMessageFactory


def test_cleanup_cleans_correctly(db_request):
    now = dt.datetime.now(dt.UTC)

    EmailMessageFactory.create(
        status="Delivered",
        created=(now - CLEANUP_DELIVERED_AFTER - dt.timedelta(hours=1)),
    )
    EmailMessageFactory.create(
        status="Bounced", created=(now - CLEANUP_AFTER - dt.timedelta(hours=1))
    )

    to_be_kept = [
        EmailMessageFactory.create(
            status="Delivered",
            created=(now - CLEANUP_DELIVERED_AFTER + dt.timedelta(hours=1)),
        ),
        EmailMessageFactory.create(
            status="Bounced",
            created=(now - CLEANUP_AFTER + dt.timedelta(hours=1)),
        ),
    ]

    cleanup(db_request)

    assert set(db_request.db.query(EmailMessage).all()) == set(to_be_kept)
