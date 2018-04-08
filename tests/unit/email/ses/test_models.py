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

import pretend
import pytest

from warehouse.email.ses.models import MAX_TRANSIENT_BOUNCES, EmailStatus

from ....common.db.accounts import EmailFactory


class TestEmailStatus:

    def test_starts_out_accepted(self):
        assert EmailStatus(pretend.stub()).save() == "Accepted"

    def test_can_deliver(self, db_session):
        email = EmailFactory.create()

        status = EmailStatus(db_session)
        status.deliver(email.email)

        assert status.save() == "Delivered"

    def test_delivery_resets_transient_bounces(self, db_session):
        email = EmailFactory.create(transient_bounces=3)

        status = EmailStatus(db_session)
        status.deliver(email.email)

        assert status.save() == "Delivered"
        assert email.transient_bounces == 0

    def test_soft_bounce_increments_transient_bounces(self, db_session):
        email = EmailFactory.create(transient_bounces=3)

        status = EmailStatus(db_session)
        status.soft_bounce(email.email)

        assert status.save() == "Soft Bounced"
        assert email.transient_bounces == 4

    def test_soft_bounced_unverifies_when_going_over(self, db_session):
        email = EmailFactory.create(transient_bounces=MAX_TRANSIENT_BOUNCES)

        status = EmailStatus(db_session)
        status.soft_bounce(email.email)

        assert status.save() == "Soft Bounced"
        assert email.transient_bounces == MAX_TRANSIENT_BOUNCES + 1
        assert not email.verified
        assert email.is_having_delivery_issues

    def test_soft_bounce_after_delivery_does_nothing(self, db_session):
        email = EmailFactory.create(transient_bounces=3)

        status = EmailStatus(db_session)
        status.deliver(email.email)
        status.soft_bounce(email.email)

        assert status.save() == "Delivered"
        assert email.transient_bounces == 0

    def test_hard_bounce_unverifies_email(self, db_session):
        email = EmailFactory.create()

        status = EmailStatus(db_session)
        status.bounce(email.email)

        assert status.save() == "Bounced"
        assert not email.verified
        assert email.is_having_delivery_issues

    def test_hard_bounce_resets_transient_bounces(self, db_session):
        email = EmailFactory.create(transient_bounces=3)

        status = EmailStatus(db_session)
        status.bounce(email.email)

        assert email.transient_bounces == 0

    def test_complain_unverifies_email(self, db_session):
        email = EmailFactory.create()

        status = EmailStatus(db_session)
        status.deliver(email.email)
        status.complain(email.email)

        assert status.save() == "Complained"
        assert not email.verified
        assert email.is_having_delivery_issues

    def test_complain_resets_transient_bounces(self, db_session):
        email = EmailFactory.create(transient_bounces=3)

        status = EmailStatus(db_session)
        status.deliver(email.email)
        status.complain(email.email)

        assert email.transient_bounces == 0

    def test_load(self):
        status = EmailStatus.load(pretend.stub(), "Delivered")
        assert status.save() == "Delivered"
