# SPDX-License-Identifier: Apache-2.0

import datetime as dt
import uuid

from unittest import mock

import pytest
import stripe

from freezegun import freeze_time
from pyramid_retry import RetryableException

from warehouse.accounts.interfaces import ITokenService, TokenExpired
from warehouse.admin.flags import AdminFlag, AdminFlagValue
from warehouse.events.tags import EventTag
from warehouse.organizations import tasks as organization_tasks
from warehouse.organizations.models import (
    OrganizationApplication,
    OrganizationApplicationStatus,
    OrganizationDeactivationNotice,
    OrganizationDeactivationReason,
    OrganizationInvitationStatus,
    OrganizationRoleType,
    OrganizationType,
)
from warehouse.organizations.tasks import (
    deactivate_unpaid_organization,
    delete_declined_organization_applications,
    reconcile_stripe_status,
    schedule_unpaid_organization_deactivations,
    send_organization_deactivation_notices,
    update_organization_invitation_status,
    update_organziation_subscription_usage_record,
)
from warehouse.subscriptions.models import StripeSubscriptionStatus

from ...common.db.accounts import EmailFactory
from ...common.db.organizations import (
    OrganizationApplicationFactory,
    OrganizationDeactivationNoticeFactory,
    OrganizationDeactivationScheduleFactory,
    OrganizationFactory,
    OrganizationInvitationFactory,
    OrganizationManualActivationFactory,
    OrganizationProjectFactory,
    OrganizationRoleFactory,
    OrganizationStripeCustomerFactory,
    OrganizationStripeSubscriptionFactory,
    UserFactory,
)
from ...common.db.subscriptions import (
    StripeCustomerFactory,
    StripeSubscriptionFactory,
    StripeSubscriptionItemFactory,
    StripeSubscriptionPriceFactory,
    StripeSubscriptionProductFactory,
)


class TestUpdateInvitationStatus:
    def test_update_invitation_status(
        self, db_request, user_service, organization_service, token_service, mocker
    ):
        organization = OrganizationFactory.create()
        org_event = mocker.patch.object(organization, "record_event", autospec=True)
        user = UserFactory.create()
        user_event = mocker.patch.object(user, "record_event", autospec=True)

        invite = OrganizationInvitationFactory(user=user, organization=organization)

        mocker.patch.object(token_service, "loads", side_effect=TokenExpired)
        find_service = mocker.spy(db_request, "find_service")

        update_organization_invitation_status(db_request)

        find_service.assert_called_once_with(ITokenService, name="email")
        assert invite.invite_status == OrganizationInvitationStatus.Expired

        user_event.assert_called_once_with(
            tag=EventTag.Account.OrganizationRoleExpireInvite,
            request=db_request,
            additional={"organization_name": invite.organization.name},
        )
        org_event.assert_called_once_with(
            tag=EventTag.Organization.OrganizationRoleExpireInvite,
            request=db_request,
            additional={"target_user_id": str(invite.user.id)},
        )

    def test_no_updates(
        self, db_request, user_service, organization_service, token_service, mocker
    ):
        organization = OrganizationFactory.create()
        org_event = mocker.patch.object(organization, "record_event", autospec=True)
        user = UserFactory.create()
        user_event = mocker.patch.object(user, "record_event", autospec=True)

        invite = OrganizationInvitationFactory(user=user, organization=organization)

        mocker.patch.object(token_service, "loads", return_value={})
        find_service = mocker.spy(db_request, "find_service")

        update_organization_invitation_status(db_request)

        find_service.assert_called_once_with(ITokenService, name="email")
        assert invite.invite_status == OrganizationInvitationStatus.Pending

        user_event.assert_not_called()
        org_event.assert_not_called()


class TestDeleteOrganizationApplications:
    def test_delete_declined_organization_applications(self, db_request):
        # Create an organization_application that's ready for cleanup
        organization_application = OrganizationApplicationFactory.create()
        organization_application.is_active = False
        organization_application.status = OrganizationApplicationStatus.Declined
        organization_application.updated = dt.datetime.now() - dt.timedelta(days=31)

        # Create an organization_application that's not ready to be cleaned up yet
        organization_application2 = OrganizationApplicationFactory.create()
        organization_application2.is_active = False
        organization_application2.status = OrganizationApplicationStatus.Declined
        organization_application2.updated = dt.datetime.now()

        assert (
            db_request.db.query(OrganizationApplication.id)
            .filter(OrganizationApplication.id == organization_application.id)
            .count()
            == 1
        )

        assert (
            db_request.db.query(OrganizationApplication.id)
            .filter(OrganizationApplication.id == organization_application2.id)
            .count()
            == 1
        )

        assert db_request.db.query(OrganizationApplication).count() == 2

        delete_declined_organization_applications(db_request)

        assert not (
            db_request.db.query(OrganizationApplication.id)
            .filter(OrganizationApplication.id == organization_application.id)
            .count()
        )

        assert (
            db_request.db.query(OrganizationApplication.id)
            .filter(OrganizationApplication.id == organization_application2.id)
            .count()
        )

        assert db_request.db.query(OrganizationApplication).count() == 1


class TestUpdateOrganizationSubscriptionUsage:
    def test_update_organization_subscription_usage_record(
        self, db_request, billing_service, mocker
    ):
        # Setup an organization with an active subscription
        organization = OrganizationFactory.create()
        owner_user = UserFactory.create()
        OrganizationRoleFactory(
            organization=organization,
            user=owner_user,
            role_name=OrganizationRoleType.Owner,
        )
        member_user = UserFactory.create()
        OrganizationRoleFactory(
            organization=organization,
            user=member_user,
            role_name=OrganizationRoleType.Member,
        )
        stripe_customer = StripeCustomerFactory.create()
        OrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )
        subscription_product = StripeSubscriptionProductFactory.create()
        subscription_price = StripeSubscriptionPriceFactory.create(
            subscription_product=subscription_product
        )
        subscription = StripeSubscriptionFactory.create(
            customer=stripe_customer,
            subscription_price=subscription_price,
        )
        OrganizationStripeSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )
        StripeSubscriptionItemFactory.create(subscription=subscription)

        # Setup an organization with a cancelled subscription
        organization = OrganizationFactory.create()
        owner_user = UserFactory.create()
        OrganizationRoleFactory(
            organization=organization,
            user=owner_user,
            role_name=OrganizationRoleType.Owner,
        )
        member_user = UserFactory.create()
        OrganizationRoleFactory(
            organization=organization,
            user=member_user,
            role_name=OrganizationRoleType.Member,
        )
        stripe_customer = StripeCustomerFactory.create()
        OrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )
        subscription_product = StripeSubscriptionProductFactory.create()
        subscription_price = StripeSubscriptionPriceFactory.create(
            subscription_product=subscription_product
        )
        subscription = StripeSubscriptionFactory.create(
            customer=stripe_customer,
            subscription_price=subscription_price,
            status=StripeSubscriptionStatus.Canceled,
        )
        OrganizationStripeSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )
        StripeSubscriptionItemFactory.create(subscription=subscription)

        create_usage_record = mocker.patch.object(
            billing_service,
            "create_or_update_usage_record",
            return_value={
                "subscription_item_id": "si_1234",
                "organization_member_count": "5",
            },
        )

        update_organziation_subscription_usage_record(db_request)

        # Only the active subscription is reported; the canceled one is skipped.
        create_usage_record.assert_called_once()

    @pytest.mark.parametrize(
        "error",
        [
            stripe.error.InvalidRequestError(
                "Cannot create the usage record because the subscription "
                "has been canceled.",
                None,
            ),
            # Not transient, but not an InvalidRequestError either.
            stripe.error.AuthenticationError("Invalid API key"),
        ],
    )
    def test_continues_when_a_subscription_fails(
        self, db_request, billing_service, metrics, mocker, error
    ):
        # First usage report raises; the batch must still report the second org.
        for _ in range(2):
            organization = OrganizationFactory.create()
            OrganizationRoleFactory(
                organization=organization,
                user=UserFactory.create(),
                role_name=OrganizationRoleType.Owner,
            )
            stripe_customer = StripeCustomerFactory.create()
            OrganizationStripeCustomerFactory.create(
                organization=organization, customer=stripe_customer
            )
            subscription_price = StripeSubscriptionPriceFactory.create(
                subscription_product=StripeSubscriptionProductFactory.create()
            )
            subscription = StripeSubscriptionFactory.create(
                customer=stripe_customer, subscription_price=subscription_price
            )
            OrganizationStripeSubscriptionFactory.create(
                organization=organization, subscription=subscription
            )
            StripeSubscriptionItemFactory.create(subscription=subscription)

        create_usage_record = mocker.patch.object(
            billing_service,
            "create_or_update_usage_record",
            side_effect=[
                error,
                {"subscription_item_id": "si_1234", "organization_member_count": "1"},
            ],
        )
        increment = mocker.spy(metrics, "increment")

        update_organziation_subscription_usage_record(db_request)

        # Both subscriptions are attempted even though the first one raised.
        assert create_usage_record.call_count == 2
        increment.assert_any_call(
            "warehouse.organizations.subscription.usage_record.error",
            tags=[f"error_type:{error.__class__.__name__}"],
        )
        increment.assert_any_call(
            "warehouse.organizations.subscription.usage_record.updated"
        )

    def test_retries_on_transient_stripe_errors(
        self, db_request, billing_service, mocker
    ):
        # A transient failure (rate limit, connection) must abort the run
        # so it retries, rather than being swallowed as a per-subscription skip.
        org_subscription = OrganizationStripeSubscriptionFactory.create()
        StripeSubscriptionItemFactory.create(subscription=org_subscription.subscription)

        mocker.patch.object(
            billing_service,
            "create_or_update_usage_record",
            side_effect=stripe.error.RateLimitError("Too many requests"),
        )

        with pytest.raises(RetryableException):
            update_organziation_subscription_usage_record(db_request)


class TestReconcileStripeStatus:
    @staticmethod
    def _make_org_subscription():
        org_subscription = OrganizationStripeSubscriptionFactory.create()
        return org_subscription.organization, org_subscription.subscription

    @staticmethod
    def _remote(*subscriptions):
        return [
            {"id": subscription.subscription_id, "status": status}
            for subscription, status in subscriptions
        ]

    def test_syncs_status_from_stripe(
        self, db_request, billing_service, metrics, mocker
    ):
        organization, subscription = self._make_org_subscription()
        record_event = mocker.patch.object(organization, "record_event", autospec=True)
        mocker.patch.object(
            billing_service,
            "list_subscriptions",
            return_value=self._remote(
                (subscription, StripeSubscriptionStatus.PastDue.value)
            ),
        )

        reconcile_stripe_status(db_request)

        assert subscription.status == StripeSubscriptionStatus.PastDue.value
        record_event.assert_called_once_with(
            tag=EventTag.Organization.SubscriptionStatusChange,
            request=db_request,
            additional={
                "subscription_id": subscription.subscription_id,
                "previous_status": StripeSubscriptionStatus.Active.value,
                "status": StripeSubscriptionStatus.PastDue.value,
            },
        )
        metrics.increment.assert_any_call(
            "warehouse.organizations.subscription.status.reconciled",
            tags=["status:past_due"],
        )

    def test_no_change_when_status_matches(
        self, db_request, billing_service, subscription_service, mocker
    ):
        organization, subscription = self._make_org_subscription()
        record_event = mocker.patch.object(organization, "record_event", autospec=True)
        sync_status = mocker.spy(subscription_service, "sync_subscription_status")
        mocker.patch.object(
            billing_service,
            "list_subscriptions",
            return_value=self._remote(
                (subscription, StripeSubscriptionStatus.Active.value)
            ),
        )

        reconcile_stripe_status(db_request)

        assert sync_status.spy_return is False
        record_event.assert_not_called()

    def test_records_cancel_when_canceled_on_stripe(
        self, db_request, billing_service, mocker
    ):
        # Cancellation is detected from the fetched status, mirroring the
        # customer.subscription.deleted webhook handler.
        organization, subscription = self._make_org_subscription()
        record_event = mocker.patch.object(organization, "record_event", autospec=True)
        mocker.patch.object(
            billing_service,
            "list_subscriptions",
            return_value=self._remote(
                (subscription, StripeSubscriptionStatus.Canceled.value)
            ),
        )

        reconcile_stripe_status(db_request)

        assert subscription.status == StripeSubscriptionStatus.Canceled.value
        record_event.assert_called_once_with(
            tag=EventTag.Organization.SubscriptionCancel,
            request=db_request,
            additional={"subscription_id": subscription.subscription_id},
        )

    def test_skips_locally_canceled_subscription(
        self, db_request, billing_service, subscription_service, mocker
    ):
        # Stripe never reactivates a canceled subscription, so canceled rows are
        # excluded up front instead of being re-checked every run.
        organization, subscription = self._make_org_subscription()
        subscription.status = StripeSubscriptionStatus.Canceled
        record_event = mocker.patch.object(organization, "record_event", autospec=True)
        sync_status = mocker.spy(subscription_service, "sync_subscription_status")
        mocker.patch.object(
            billing_service,
            "list_subscriptions",
            return_value=self._remote(
                (subscription, StripeSubscriptionStatus.Active.value)
            ),
        )

        reconcile_stripe_status(db_request)

        sync_status.assert_not_called()
        record_event.assert_not_called()
        assert subscription.status == StripeSubscriptionStatus.Canceled

    def test_retries_on_transient_stripe_errors(
        self, db_request, billing_service, mocker
    ):
        self._make_org_subscription()

        # Paging is lazy, so a transient error surfaces while the results are
        # being consumed rather than when list_subscriptions is called.
        def pages():
            yield {"id": "sub_first", "status": StripeSubscriptionStatus.Active.value}
            raise stripe.error.RateLimitError("Too many requests")

        mocker.patch.object(billing_service, "list_subscriptions", side_effect=pages)

        with pytest.raises(RetryableException):
            reconcile_stripe_status(db_request)

    def test_skips_subscription_missing_from_stripe(
        self, db_request, billing_service, metrics, mocker
    ):
        # An id Stripe has no record of must be left alone rather than canceled,
        # so a mode/account-mismatched key can't mass-cancel every subscription.
        _, missing_subscription = self._make_org_subscription()
        _, known_subscription = self._make_org_subscription()
        mocker.patch.object(
            billing_service,
            "list_subscriptions",
            return_value=self._remote(
                (known_subscription, StripeSubscriptionStatus.Canceled.value)
            ),
        )

        reconcile_stripe_status(db_request)

        assert missing_subscription.status == StripeSubscriptionStatus.Active.value
        assert known_subscription.status == StripeSubscriptionStatus.Canceled.value
        metrics.increment.assert_any_call(
            "warehouse.organizations.subscription.status.reconcile.missing"
        )

    def test_raises_when_no_subscription_found_on_stripe(
        self, db_request, billing_service, subscription_service, mocker
    ):
        # A key for the wrong account or mode matches nothing; that must fail the
        # run instead of quietly skipping every row.
        self._make_org_subscription()
        self._make_org_subscription()
        sync_status = mocker.spy(subscription_service, "sync_subscription_status")
        mocker.patch.object(
            billing_service,
            "list_subscriptions",
            return_value=[
                {"id": "sub_other", "status": StripeSubscriptionStatus.Active.value}
            ],
        )

        with pytest.raises(RuntimeError, match="None of 2 subscriptions"):
            reconcile_stripe_status(db_request)

        sync_status.assert_not_called()

    def test_skips_unknown_status(
        self, db_request, billing_service, subscription_service, metrics, mocker
    ):
        _, subscription = self._make_org_subscription()
        sync_status = mocker.spy(subscription_service, "sync_subscription_status")
        mocker.patch.object(
            billing_service,
            "list_subscriptions",
            return_value=self._remote((subscription, "bogus")),
        )

        reconcile_stripe_status(db_request)

        sync_status.assert_not_called()
        metrics.increment.assert_any_call(
            "warehouse.organizations.subscription.status.reconcile.skipped",
            tags=["remote_status:bogus"],
        )
        assert subscription.status == StripeSubscriptionStatus.Active.value


TODAY = dt.date(2026, 10, 17)


def _unpaid_org(**kwargs):
    organization = OrganizationFactory.create(
        orgtype=OrganizationType.Company, **kwargs
    )
    owner = UserFactory.create(with_verified_primary_email=True)
    OrganizationRoleFactory.create(organization=organization, user=owner)
    return organization, owner


def _unverified_owner(organization, *, other_verified=False):
    owner = UserFactory.create()
    EmailFactory.create(user=owner, verified=False, primary=True)
    other = (
        EmailFactory.create(user=owner, verified=True, primary=False)
        if other_verified
        else None
    )
    OrganizationRoleFactory.create(organization=organization, user=owner)
    return owner, other


def _schedule(organization, *, deactivate_in, last_notice_days):
    return OrganizationDeactivationScheduleFactory.create(
        organization=organization,
        deactivate_on=TODAY + dt.timedelta(days=deactivate_in),
        last_notice_days=last_notice_days,
    )


@freeze_time(TODAY.isoformat() + " 01:00:00")
class TestScheduleUnpaidOrganizationDeactivations:
    def test_processes_unpaid_and_scheduled_orgs(self, db_request):
        unpaid, _ = _unpaid_org()
        canceled, _ = _unpaid_org()
        OrganizationStripeSubscriptionFactory.create(
            organization=canceled,
            subscription__status=StripeSubscriptionStatus.Canceled,
        )
        # Scheduled orgs are still processed once they no longer qualify.
        scheduled_inactive, _ = _unpaid_org(is_active=False)
        _schedule(scheduled_inactive, deactivate_in=14, last_notice_days=30)
        # An owner reachable only at a non-primary verified address counts.
        secondary_only = OrganizationFactory.create(orgtype=OrganizationType.Company)
        _unverified_owner(secondary_only, other_verified=True)

        # Nobody can be told, but they own nothing, so they're deactivated anyway.
        unreachable = OrganizationFactory.create(orgtype=OrganizationType.Company)
        _unverified_owner(unreachable)
        ownerless = OrganizationFactory.create(orgtype=OrganizationType.Company)

        # Payment recovery uses the same bounded countdown as other unpaid orgs.
        past_due, _ = _unpaid_org()
        OrganizationStripeSubscriptionFactory.create(
            organization=past_due,
            subscription__status=StripeSubscriptionStatus.PastDue,
        )
        # None of these are processed.
        good_standing, _ = _unpaid_org()
        OrganizationManualActivationFactory.create(organization=good_standing)
        OrganizationFactory.create(orgtype=OrganizationType.Community)
        _unpaid_org(is_active=False)
        _unpaid_org(created=dt.datetime.now(dt.UTC))
        # Nobody can be told and it owns a project.
        unreachable_with_project = OrganizationFactory.create(
            orgtype=OrganizationType.Company
        )
        _unverified_owner(unreachable_with_project)
        OrganizationProjectFactory.create(organization=unreachable_with_project)

        schedule_unpaid_organization_deactivations(db_request)

        db_request.db.flush()
        db_request.db.expire(scheduled_inactive)

        assert scheduled_inactive.deactivation_schedule is None
        assert {organization_id for organization_id, _ in _queued(db_request)} == {
            unpaid.id,
            canceled.id,
            secondary_only.id,
            unreachable.id,
            ownerless.id,
            past_due.id,
        }

    def test_caps_new_notice_periods_oldest_first(self, db_request, mocker):
        mocker.patch("warehouse.organizations.tasks.DEACTIVATION_STARTS_PER_DAY", 1)

        oldest, _ = _unpaid_org(created=dt.datetime(2021, 1, 1))
        _unpaid_org(created=dt.datetime(2022, 1, 1))
        # Orgs already counting down don't count against the cap.
        scheduled, _ = _unpaid_org(created=dt.datetime(2023, 1, 1))
        _schedule(scheduled, deactivate_in=14, last_notice_days=30)

        schedule_unpaid_organization_deactivations(db_request)

        assert {organization_id for organization_id, _ in _queued(db_request)} == {
            oldest.id,
            scheduled.id,
        }

    def test_failed_producer_rolls_back_the_batch(self, db_request, mocker):
        first, _ = _unpaid_org(created=dt.datetime(2021, 1, 1))
        second, _ = _unpaid_org(created=dt.datetime(2022, 1, 1))
        queue_reminder = organization_tasks._queue_reminder

        def fail_after_queueing(request, schedule):
            queue_reminder(request, schedule)
            if schedule.organization is second:
                raise RuntimeError("producer failed")

        mocker.patch.object(
            organization_tasks, "_queue_reminder", side_effect=fail_after_queueing
        )
        task = mocker.patch.object(db_request, "task")

        with (
            pytest.raises(RuntimeError, match="producer failed"),
            db_request.db.begin_nested(),
        ):
            schedule_unpaid_organization_deactivations(db_request)

        db_request.db.expire_all()
        assert first.deactivation_schedule is None
        assert second.deactivation_schedule is None
        assert _queued(db_request) == []
        task.assert_not_called()

    def test_disallowed_by_admin_flag(self, db_request):
        db_request.db.get(
            AdminFlag, AdminFlagValue.DISALLOW_ORGANIZATION_DEACTIVATION.value
        ).enabled = True
        organization, _ = _unpaid_org()

        schedule_unpaid_organization_deactivations(db_request)

        assert organization.deactivation_schedule is None
        assert _queued(db_request) == []


def _queued(db_request):
    return sorted(
        (notice.organization_id, notice.deactivated)
        for notice in db_request.db.query(OrganizationDeactivationNotice)
    )


@freeze_time(TODAY.isoformat() + " 01:00:00")
class TestDeactivateUnpaidOrganization:
    @pytest.mark.parametrize(
        "status",
        [
            None,
            StripeSubscriptionStatus.PastDue,
            StripeSubscriptionStatus.Unpaid,
            StripeSubscriptionStatus.Incomplete,
        ],
    )
    def test_starts_notice_period(self, db_request, metrics, status):
        organization, _ = _unpaid_org()
        if status is not None:
            OrganizationStripeSubscriptionFactory.create(
                organization=organization, subscription__status=status
            )

        deactivate_unpaid_organization(db_request, organization.id)

        schedule = organization.deactivation_schedule
        assert schedule.deactivate_on == TODAY + dt.timedelta(days=30)
        assert schedule.last_notice_days == 30
        assert _queued(db_request) == [(organization.id, False)]
        metrics.increment.assert_any_call(
            "warehouse.organizations.deactivation.notice", tags=["days:30"]
        )

    @pytest.mark.parametrize("has_owner", [True, False])
    def test_unreachable_org_without_projects_starts_notice_period(
        self, db_request, has_owner
    ):
        organization = OrganizationFactory.create(orgtype=OrganizationType.Company)
        if has_owner:
            _unverified_owner(organization)

        deactivate_unpaid_organization(db_request, organization.id)

        assert organization.deactivation_schedule is not None
        assert _queued(db_request) == [(organization.id, False)]

    # The owner can also lose their last verified address mid-countdown.
    @pytest.mark.parametrize("deactivate_in", [None, -1])
    def test_unreachable_org_with_projects_is_skipped(
        self, db_request, metrics, deactivate_in
    ):
        organization = OrganizationFactory.create(orgtype=OrganizationType.Company)
        _unverified_owner(organization)
        OrganizationProjectFactory.create(organization=organization)
        if deactivate_in is not None:
            _schedule(organization, deactivate_in=deactivate_in, last_notice_days=3)

        deactivate_unpaid_organization(db_request, organization.id)
        db_request.db.flush()
        db_request.db.expire(organization)

        assert organization.is_active
        assert organization.deactivation_schedule is None
        assert _queued(db_request) == []
        metrics.increment.assert_any_call(
            "warehouse.organizations.deactivation.skipped",
            tags=["reason:no_recipients"],
        )

    @pytest.mark.parametrize(
        ("deactivate_in", "last_notice_days", "notice_days", "new_deactivate_in"),
        [
            (14, 30, 14, 14),
            (3, 14, 3, 3),
            # Late reminders never shorten the notice they promise.
            (10, 30, 14, 14),
            (-5, 14, 3, 3),
            # A missed reminder starts the notice period over.
            (1, 30, 30, 30),
            (-5, 30, 30, 30),
        ],
    )
    def test_queues_due_reminder(
        self,
        db_request,
        metrics,
        deactivate_in,
        last_notice_days,
        notice_days,
        new_deactivate_in,
    ):
        organization, _ = _unpaid_org()
        schedule = _schedule(
            organization,
            deactivate_in=deactivate_in,
            last_notice_days=last_notice_days,
        )

        deactivate_unpaid_organization(db_request, organization.id)

        assert organization.is_active
        assert schedule.last_notice_days == notice_days
        assert schedule.deactivate_on == TODAY + dt.timedelta(days=new_deactivate_in)
        assert _queued(db_request) == [(organization.id, False)]
        metrics.increment.assert_any_call(
            "warehouse.organizations.deactivation.notice",
            tags=[f"days:{notice_days}"],
        )

    @pytest.mark.parametrize(
        ("deactivate_in", "last_notice_days"),
        [(30, 30), (5, 14), (0, 3)],
    )
    def test_waits_between_reminders(self, db_request, deactivate_in, last_notice_days):
        organization, _ = _unpaid_org()
        schedule = _schedule(
            organization,
            deactivate_in=deactivate_in,
            last_notice_days=last_notice_days,
        )

        deactivate_unpaid_organization(db_request, organization.id)

        assert organization.is_active
        assert schedule.last_notice_days == last_notice_days
        assert _queued(db_request) == []

    def test_deactivates_after_final_notice(self, db_request, metrics):
        organization, _ = _unpaid_org()
        _schedule(organization, deactivate_in=-1, last_notice_days=3)

        deactivate_unpaid_organization(db_request, organization.id)
        db_request.db.flush()
        db_request.db.expire(organization)

        assert not organization.is_active
        assert (
            organization.deactivated_reason == OrganizationDeactivationReason.NoPaidSeat
        )
        assert organization.deactivated == dt.datetime(2026, 10, 17, 1, tzinfo=dt.UTC)
        assert organization.deactivation_schedule is None
        assert (
            organization.events.filter_by(
                tag=EventTag.Organization.OrganizationDeactivate
            )
            .one()
            .additional["reason"]
            == "no_paid_seat"
        )
        assert _queued(db_request) == [(organization.id, True)]
        metrics.increment.assert_any_call(
            "warehouse.organizations.deactivation.deactivated"
        )

    @pytest.mark.parametrize(
        ("status", "clears"),
        [
            (StripeSubscriptionStatus.Active, True),
            (StripeSubscriptionStatus.Trialing, True),
            (StripeSubscriptionStatus.PastDue, False),
            (StripeSubscriptionStatus.Unpaid, False),
            (StripeSubscriptionStatus.Incomplete, False),
        ],
    )
    def test_subscription_status_updates_countdown(
        self, db_request, metrics, status, clears
    ):
        organization, _ = _unpaid_org()
        _schedule(organization, deactivate_in=3, last_notice_days=14)
        OrganizationStripeSubscriptionFactory.create(
            organization=organization, subscription__status=status
        )

        deactivate_unpaid_organization(db_request, organization.id)
        db_request.db.flush()
        db_request.db.expire(organization)

        assert organization.is_active
        if clears:
            assert organization.deactivation_schedule is None
            assert _queued(db_request) == []
            metrics.increment.assert_any_call(
                "warehouse.organizations.deactivation.cleared"
            )
        else:
            assert organization.deactivation_schedule.last_notice_days == 3
            assert _queued(db_request) == [(organization.id, False)]

    def test_ignores_org_in_good_standing(self, db_request, metrics):
        organization, _ = _unpaid_org()
        OrganizationManualActivationFactory.create(organization=organization)

        deactivate_unpaid_organization(db_request, organization.id)

        assert organization.deactivation_schedule is None
        assert _queued(db_request) == []
        assert (
            mock.call("warehouse.organizations.deactivation.cleared")
            not in metrics.increment.call_args_list
        )

    def test_ignores_missing_org(self, db_request):
        deactivate_unpaid_organization(db_request, uuid.uuid4())

        assert _queued(db_request) == []

    def test_disallowed_by_admin_flag(self, db_request):
        db_request.db.get(
            AdminFlag, AdminFlagValue.DISALLOW_ORGANIZATION_DEACTIVATION.value
        ).enabled = True
        organization, _ = _unpaid_org()

        deactivate_unpaid_organization(db_request, organization.id)

        assert organization.deactivation_schedule is None
        assert _queued(db_request) == []


@freeze_time(TODAY.isoformat() + " 02:00:00")
class TestSendOrganizationDeactivationNotices:
    @pytest.fixture
    def send_reminder(self, mocker):
        return mocker.patch(
            "warehouse.organizations.tasks."
            "send_organization_subscription_required_email",
        )

    @pytest.fixture
    def send_deactivated(self, mocker):
        return mocker.patch(
            "warehouse.organizations.tasks.send_organization_deactivated_email",
        )

    def test_sends_each_owner_one_email_per_kind(
        self, db_request, send_reminder, send_deactivated
    ):
        later, owner = _unpaid_org(name="later")
        _schedule(later, deactivate_in=14, last_notice_days=14)
        sooner = OrganizationFactory.create(
            orgtype=OrganizationType.Company, name="sooner"
        )
        # Reached at their other verified address; the unreachable owner is skipped.
        sooner_owner, sooner_email = _unverified_owner(sooner, other_verified=True)
        _unverified_owner(sooner)
        _schedule(sooner, deactivate_in=3, last_notice_days=3)
        OrganizationRoleFactory.create(organization=sooner, user=owner)
        gone, _ = _unpaid_org(name="gone")
        gone.deactivate(OrganizationDeactivationReason.NoPaidSeat)
        OrganizationRoleFactory.create(organization=gone, user=owner)
        # Only owners are told.
        OrganizationRoleFactory.create(
            organization=later, role_name=OrganizationRoleType.Member
        )
        for organization, deactivated in (
            (later, False),
            (sooner, False),
            (gone, True),
        ):
            OrganizationDeactivationNoticeFactory.create(
                organization=organization, deactivated=deactivated
            )
        # A duplicate notice still means one entry.
        OrganizationDeactivationNoticeFactory.create(organization=later)

        send_organization_deactivation_notices(db_request)

        assert send_reminder.call_count == 2
        send_reminder.assert_any_call(
            db_request,
            (owner, owner.primary_email),
            organizations=[
                {
                    "name": "sooner",
                    "deactivate_on": TODAY + dt.timedelta(days=3),
                    "days_remaining": 3,
                },
                {
                    "name": "later",
                    "deactivate_on": TODAY + dt.timedelta(days=14),
                    "days_remaining": 14,
                },
            ],
        )
        send_reminder.assert_any_call(
            db_request,
            (sooner_owner, sooner_email),
            organizations=[
                {
                    "name": "sooner",
                    "deactivate_on": TODAY + dt.timedelta(days=3),
                    "days_remaining": 3,
                }
            ],
        )
        # gone's own owner gets the other deactivated email.
        assert send_deactivated.call_count == 2
        send_deactivated.assert_any_call(
            db_request,
            (owner, owner.primary_email),
            organizations=[
                {"name": "gone", "reactivate_by": TODAY + dt.timedelta(days=90)}
            ],
        )
        assert _queued(db_request) == []

    def test_drops_notices_no_longer_needed(
        self, db_request, send_reminder, send_deactivated
    ):
        paid, _ = _unpaid_org()
        OrganizationManualActivationFactory.create(organization=paid)
        OrganizationDeactivationNoticeFactory.create(organization=paid)
        reactivated, _ = _unpaid_org()
        OrganizationDeactivationNoticeFactory.create(
            organization=reactivated, deactivated=True
        )
        # Orgs owners can no longer reactivate by paying get no deactivated email.
        owner_removed, _ = _unpaid_org()
        owner_removed.deactivate(OrganizationDeactivationReason.OwnerRemoved)
        lapsed, _ = _unpaid_org()
        lapsed.deactivate(OrganizationDeactivationReason.NoPaidSeat)
        lapsed.deactivated -= dt.timedelta(days=91)
        for organization in (owner_removed, lapsed):
            OrganizationDeactivationNoticeFactory.create(
                organization=organization, deactivated=True
            )

        send_organization_deactivation_notices(db_request)

        send_reminder.assert_not_called()
        send_deactivated.assert_not_called()
        assert _queued(db_request) == []

    def test_disallowed_by_admin_flag(
        self, db_request, send_reminder, send_deactivated
    ):
        db_request.db.get(
            AdminFlag, AdminFlagValue.DISALLOW_ORGANIZATION_DEACTIVATION.value
        ).enabled = True
        organization, _ = _unpaid_org()
        _schedule(organization, deactivate_in=30, last_notice_days=30)
        OrganizationDeactivationNoticeFactory.create(organization=organization)

        send_organization_deactivation_notices(db_request)

        send_reminder.assert_not_called()
        assert _queued(db_request) == [(organization.id, False)]
