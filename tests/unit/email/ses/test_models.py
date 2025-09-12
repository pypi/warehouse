# SPDX-License-Identifier: Apache-2.0

import pytest

from warehouse.accounts.models import UnverifyReasons
from warehouse.email.ses.models import (
    MAX_TRANSIENT_BOUNCES,
    EmailMessage,
    EmailStatus,
    EmailStatuses,
)

from ....common.db.accounts import EmailFactory
from ....common.db.ses import EmailMessageFactory


class TestEmailStatus:
    def test_starts_out_accepted(self, db_session):
        em = EmailStatus(EmailMessage()).save()
        assert em.status is EmailStatuses.Accepted

    def test_can_deliver(self, db_session):
        email = EmailFactory.create()
        em = EmailMessageFactory.create(to=email.email)

        status = EmailStatus.load(em)
        status.deliver()

        assert status.save().status is EmailStatuses.Delivered
        assert email.unverify_reason is None

    def test_delivery_resets_transient_bounces(self, db_session):
        email = EmailFactory.create(transient_bounces=3)
        em = EmailMessageFactory.create(to=email.email)

        status = EmailStatus.load(em)
        status.deliver()

        assert status.save().status is EmailStatuses.Delivered
        assert email.transient_bounces == 0

    def test_delivery_without_an_email_obj(self, db_session):
        em = EmailMessageFactory.create()

        status = EmailStatus.load(em)
        status.deliver()

        assert em.missing

    def test_soft_bounce_increments_transient_bounces(self, db_session):
        email = EmailFactory.create(transient_bounces=3)
        em = EmailMessageFactory.create(to=email.email)

        status = EmailStatus.load(em)
        status.soft_bounce()

        assert status.save().status is EmailStatuses.SoftBounced
        assert email.transient_bounces == 4

    def test_soft_bounced_unverifies_when_going_over(self, db_session):
        email = EmailFactory.create(transient_bounces=MAX_TRANSIENT_BOUNCES)
        em = EmailMessageFactory.create(to=email.email)

        status = EmailStatus.load(em)
        status.soft_bounce()

        assert status.save().status is EmailStatuses.SoftBounced
        assert email.transient_bounces == MAX_TRANSIENT_BOUNCES + 1
        assert not email.verified
        assert email.unverify_reason is UnverifyReasons.SoftBounce

    def test_soft_bounce_after_delivery_does_nothing(self, db_session):
        email = EmailFactory.create(transient_bounces=3)
        em = EmailMessageFactory.create(to=email.email)

        status = EmailStatus.load(em)
        status.deliver()
        status.soft_bounce()

        assert status.save().status is EmailStatuses.Delivered
        assert email.transient_bounces == 0

    def test_duplicate_delivery_does_nothing(self, db_session):
        email = EmailFactory.create()
        em = EmailMessageFactory.create(to=email.email)

        status = EmailStatus.load(em)
        status.deliver()
        status.deliver()

        assert status.save().status is EmailStatuses.Delivered

    def test_delivery_after_soft_bounce(self, db_session):
        email = EmailFactory.create()
        em = EmailMessageFactory.create(to=email.email)

        status = EmailStatus.load(em)
        status.soft_bounce()

        assert status.save().status is EmailStatuses.SoftBounced
        assert email.transient_bounces == 1

        status.deliver()

        assert status.save().status is EmailStatuses.Delivered
        assert email.transient_bounces == 0

    def test_soft_bounce_without_an_email_obj(self, db_session):
        em = EmailMessageFactory.create()

        status = EmailStatus.load(em)
        status.soft_bounce()

        assert em.missing

    def test_hard_bounce_unverifies_email(self, db_session):
        email = EmailFactory.create()
        em = EmailMessageFactory.create(to=email.email)

        status = EmailStatus.load(em)
        status.bounce()

        assert status.save().status is EmailStatuses.Bounced
        assert not email.verified
        assert email.unverify_reason is UnverifyReasons.HardBounce

    def test_hard_bounce_resets_transient_bounces(self, db_session):
        email = EmailFactory.create(transient_bounces=3)
        em = EmailMessageFactory.create(to=email.email)

        status = EmailStatus.load(em)
        status.bounce()

        assert email.transient_bounces == 0

    def test_hard_bounce_after_delivery_unverifies_email(self, db_session):
        email = EmailFactory.create()
        em = EmailMessageFactory.create(to=email.email)

        status = EmailStatus.load(em)
        status.deliver()
        status.bounce()

        assert status.save().status is EmailStatuses.Bounced
        assert not email.verified
        assert email.unverify_reason is UnverifyReasons.HardBounce

    def test_hard_bounce_after_delivery_resets_transient_bounces(self, db_session):
        email = EmailFactory.create(transient_bounces=3)
        em = EmailMessageFactory.create(to=email.email)

        status = EmailStatus.load(em)
        status.deliver()
        status.bounce()

        assert email.transient_bounces == 0

    def test_hard_bounce_without_an_email_obj(self, db_session):
        em = EmailMessageFactory.create()

        status = EmailStatus.load(em)
        status.bounce()

        assert em.missing

    def test_hard_bounce_after_delivery_without_email_obj(self, db_session):
        em = EmailMessageFactory.create()

        status = EmailStatus.load(em)
        status.deliver()
        EmailFactory.create(email=em.to)
        status.bounce()

        assert em.missing

    def test_complain_unverifies_email(self, db_session):
        email = EmailFactory.create()
        em = EmailMessageFactory.create(to=email.email)

        status = EmailStatus.load(em)
        status.deliver()
        status.complain()

        assert status.save().status is EmailStatuses.Complained
        assert not email.verified
        assert email.unverify_reason is UnverifyReasons.SpamComplaint

    def test_complain_resets_transient_bounces(self, db_session):
        email = EmailFactory.create(transient_bounces=3)
        em = EmailMessageFactory.create(to=email.email)

        status = EmailStatus.load(em)
        status.deliver()
        status.complain()

        assert email.transient_bounces == 0

    def test_complain_without_an_email_obj(self, db_session):
        em = EmailMessageFactory.create()

        status = EmailStatus.load(em)
        status.deliver()
        status.complain()

        assert em.missing

    def test_complain_without_email_obj_and_with(self, db_session):
        em = EmailMessageFactory.create()

        status = EmailStatus.load(em)
        status.deliver()
        EmailFactory.create(email=em.to)
        status.complain()

        assert em.missing

    def test_delivery_after_hard_bounce(self, db_session):
        email = EmailFactory.create(transient_bounces=3)
        em = EmailMessageFactory.create(to=email.email)

        status = EmailStatus.load(em)
        status.bounce()
        status.deliver()

        assert email.transient_bounces == 0
        assert not email.verified

    @pytest.mark.parametrize(
        "start_status",
        ["Accepted", "Delivered", "Bounced", "Soft Bounced", "Complained"],
    )
    def test_load(self, start_status, db_session):
        em = EmailMessageFactory.create(status=EmailStatuses(start_status))
        status = EmailStatus.load(em)
        assert status.save().status == EmailStatuses(start_status)
