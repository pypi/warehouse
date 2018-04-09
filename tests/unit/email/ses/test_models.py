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

import pytest

from warehouse.email.ses.models import (
    MAX_TRANSIENT_BOUNCES, EmailStatus, EmailMessage,
)

from ....common.db.accounts import EmailFactory
from ....common.db.ses import EmailMessageFactory


class TestEmailStatus:

    def test_starts_out_accepted(self, db_session):
        em = EmailStatus(EmailMessage()).save()
        assert em.status == "Accepted"

    def test_can_deliver(self, db_session):
        email = EmailFactory.create()
        em = EmailMessageFactory.create(to=email.email)

        status = EmailStatus.load(em)
        status.deliver()

        assert status.save().status == "Delivered"
        assert not email.is_having_delivery_issues
        assert not email.spam_complaint

    def test_delivery_resets_transient_bounces(self, db_session):
        email = EmailFactory.create(transient_bounces=3)
        em = EmailMessageFactory.create(to=email.email)

        status = EmailStatus.load(em)
        status.deliver()

        assert status.save().status == "Delivered"
        assert email.transient_bounces == 0

    def test_soft_bounce_increments_transient_bounces(self, db_session):
        email = EmailFactory.create(transient_bounces=3)
        em = EmailMessageFactory.create(to=email.email)

        status = EmailStatus.load(em)
        status.soft_bounce()

        assert status.save().status == "Soft Bounced"
        assert email.transient_bounces == 4

    def test_soft_bounced_unverifies_when_going_over(self, db_session):
        email = EmailFactory.create(transient_bounces=MAX_TRANSIENT_BOUNCES)
        em = EmailMessageFactory.create(to=email.email)

        status = EmailStatus.load(em)
        status.soft_bounce()

        assert status.save().status == "Soft Bounced"
        assert email.transient_bounces == MAX_TRANSIENT_BOUNCES + 1
        assert not email.verified
        assert email.is_having_delivery_issues
        assert not email.spam_complaint

    def test_soft_bounce_after_delivery_does_nothing(self, db_session):
        email = EmailFactory.create(transient_bounces=3)
        em = EmailMessageFactory.create(to=email.email)

        status = EmailStatus.load(em)
        status.deliver()
        status.soft_bounce()

        assert status.save().status == "Delivered"
        assert email.transient_bounces == 0

    def test_hard_bounce_unverifies_email(self, db_session):
        email = EmailFactory.create()
        em = EmailMessageFactory.create(to=email.email)

        status = EmailStatus.load(em)
        status.bounce()

        assert status.save().status == "Bounced"
        assert not email.verified
        assert email.is_having_delivery_issues
        assert not email.spam_complaint

    def test_hard_bounce_resets_transient_bounces(self, db_session):
        email = EmailFactory.create(transient_bounces=3)
        em = EmailMessageFactory.create(to=email.email)

        status = EmailStatus.load(em)
        status.bounce()

        assert email.transient_bounces == 0

    def test_complain_unverifies_email(self, db_session):
        email = EmailFactory.create()
        em = EmailMessageFactory.create(to=email.email)

        status = EmailStatus.load(em)
        status.deliver()
        status.complain()

        assert status.save().status == "Complained"
        assert not email.verified
        assert not email.is_having_delivery_issues
        assert email.spam_complaint

    def test_complain_resets_transient_bounces(self, db_session):
        email = EmailFactory.create(transient_bounces=3)
        em = EmailMessageFactory.create(to=email.email)

        status = EmailStatus.load(em)
        status.deliver()
        status.complain()

        assert email.transient_bounces == 0

    @pytest.mark.parametrize(
        "start_status",
        ["Accepted", "Delivered", "Bounced", "Soft Bounced", "Complained"],
    )
    def test_load(self, start_status, db_session):
        em = EmailMessageFactory.create(status=start_status)
        status = EmailStatus.load(em)
        assert status.save().status == start_status
