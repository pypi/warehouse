# SPDX-License-Identifier: Apache-2.0

import datetime

import pytest
import stripe

from pyramid_retry import RetryableException

from warehouse.accounts.interfaces import ITokenService, TokenExpired
from warehouse.events.tags import EventTag
from warehouse.organizations.models import (
    OrganizationApplication,
    OrganizationApplicationStatus,
    OrganizationInvitationStatus,
    OrganizationRoleType,
    OrganizationType,
)
from warehouse.organizations.tasks import (
    delete_declined_organization_applications,
    notify_organizations_requiring_subscription,
    reconcile_stripe_status,
    update_organization_invitation_status,
    update_organziation_subscription_usage_record,
)
from warehouse.subscriptions.models import StripeSubscriptionStatus

from ...common.db.organizations import (
    OrganizationApplicationFactory,
    OrganizationFactory,
    OrganizationInvitationFactory,
    OrganizationManualActivationFactory,
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
        organization_application.updated = datetime.datetime.now() - datetime.timedelta(
            days=31
        )

        # Create an organization_application that's not ready to be cleaned up yet
        organization_application2 = OrganizationApplicationFactory.create()
        organization_application2.is_active = False
        organization_application2.status = OrganizationApplicationStatus.Declined
        organization_application2.updated = datetime.datetime.now()

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

    def test_continues_when_a_subscription_fails(
        self, db_request, billing_service, metrics, mocker
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
                stripe.error.InvalidRequestError(
                    "Cannot create the usage record because the subscription "
                    "has been canceled.",
                    None,
                ),
                {"subscription_item_id": "si_1234", "organization_member_count": "1"},
            ],
        )
        increment = mocker.spy(metrics, "increment")

        update_organziation_subscription_usage_record(db_request)

        # Both subscriptions are attempted even though the first one raised.
        assert create_usage_record.call_count == 2
        increment.assert_any_call(
            "warehouse.organizations.subscription.usage_record.error",
            tags=["error_type:InvalidRequestError"],
        )
        increment.assert_any_call(
            "warehouse.organizations.subscription.usage_record.updated"
        )

    def test_retries_on_transient_stripe_errors(
        self, db_request, billing_service, mocker
    ):
        # A transient failure (rate limit, connection) must abort the run
        # so it retries, rather than being swallowed as a per-subscription skip.
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

        mocker.patch.object(
            billing_service,
            "create_or_update_usage_record",
            side_effect=stripe.error.RateLimitError("Too many requests"),
        )

        with pytest.raises(RetryableException):
            update_organziation_subscription_usage_record(db_request)


class TestReconcileStripeStatus:
    @staticmethod
    def _make_org_subscription(status=StripeSubscriptionStatus.Active):
        organization = OrganizationFactory.create()
        stripe_customer = StripeCustomerFactory.create()
        OrganizationStripeCustomerFactory.create(
            organization=organization, customer=stripe_customer
        )
        subscription = StripeSubscriptionFactory.create(
            customer=stripe_customer,
            subscription_price=StripeSubscriptionPriceFactory.create(
                subscription_product=StripeSubscriptionProductFactory.create()
            ),
            status=status,
        )
        OrganizationStripeSubscriptionFactory.create(
            organization=organization, subscription=subscription
        )
        return organization, subscription

    def test_syncs_status_from_stripe(
        self, db_request, billing_service, subscription_service, metrics, mocker
    ):
        organization, subscription = self._make_org_subscription()
        record_event = mocker.patch.object(organization, "record_event", autospec=True)
        mocker.patch.object(
            billing_service,
            "retrieve_subscription",
            return_value={"status": StripeSubscriptionStatus.Canceled.value},
        )
        increment = mocker.spy(metrics, "increment")

        reconcile_stripe_status(db_request)

        assert subscription.status == StripeSubscriptionStatus.Canceled.value
        record_event.assert_called_once_with(
            tag=EventTag.Organization.SubscriptionStatusChange,
            request=db_request,
            additional={
                "subscription_id": subscription.subscription_id,
                "previous_status": StripeSubscriptionStatus.Active.value,
                "status": StripeSubscriptionStatus.Canceled.value,
            },
        )
        increment.assert_any_call(
            "warehouse.organizations.subscription.status.reconciled",
            tags=["status:canceled"],
        )

    def test_no_change_when_status_matches(
        self, db_request, billing_service, subscription_service, mocker
    ):
        organization, _ = self._make_org_subscription()
        record_event = mocker.patch.object(organization, "record_event", autospec=True)
        update_status = mocker.spy(subscription_service, "update_subscription_status")
        mocker.patch.object(
            billing_service,
            "retrieve_subscription",
            return_value={"status": StripeSubscriptionStatus.Active.value},
        )

        reconcile_stripe_status(db_request)

        update_status.assert_not_called()
        record_event.assert_not_called()

    def test_marks_canceled_when_missing_on_stripe(
        self, db_request, billing_service, subscription_service, mocker
    ):
        organization, subscription = self._make_org_subscription()
        record_event = mocker.patch.object(organization, "record_event", autospec=True)
        mocker.patch.object(
            billing_service,
            "retrieve_subscription",
            side_effect=stripe.error.InvalidRequestError(
                "No such subscription", None, code="resource_missing"
            ),
        )

        reconcile_stripe_status(db_request)

        assert subscription.status == StripeSubscriptionStatus.Canceled.value
        record_event.assert_called_once_with(
            tag=EventTag.Organization.SubscriptionCancel,
            request=db_request,
            additional={"subscription_id": subscription.subscription_id},
        )

    def test_reraises_non_missing_invalid_request_errors(
        self, db_request, billing_service, subscription_service, mocker
    ):
        _, subscription = self._make_org_subscription()
        mocker.patch.object(
            billing_service,
            "retrieve_subscription",
            side_effect=stripe.error.InvalidRequestError(
                "Invalid API version", None, code="invalid_request_error"
            ),
        )

        with pytest.raises(stripe.error.InvalidRequestError):
            reconcile_stripe_status(db_request)

        assert subscription.status == StripeSubscriptionStatus.Active.value

    def test_retries_on_transient_stripe_errors(
        self, db_request, billing_service, subscription_service, mocker
    ):
        _, subscription = self._make_org_subscription()
        mocker.patch.object(
            billing_service,
            "retrieve_subscription",
            side_effect=stripe.error.RateLimitError("Too many requests"),
        )

        with pytest.raises(RetryableException):
            reconcile_stripe_status(db_request)

        assert subscription.status == StripeSubscriptionStatus.Active.value

    def test_skips_unknown_status(
        self, db_request, billing_service, subscription_service, metrics, mocker
    ):
        _, subscription = self._make_org_subscription()
        update_status = mocker.spy(subscription_service, "update_subscription_status")
        mocker.patch.object(
            billing_service, "retrieve_subscription", return_value={"status": "bogus"}
        )
        increment = mocker.spy(metrics, "increment")

        reconcile_stripe_status(db_request)

        update_status.assert_not_called()
        increment.assert_any_call(
            "warehouse.organizations.subscription.status.reconcile.skipped"
        )
        assert subscription.status == StripeSubscriptionStatus.Active.value


class TestNotifyOrganizationsRequiringSubscription:
    def test_notifies_owners_of_company_orgs_not_in_good_standing(
        self, db_request, mocker
    ):
        send_email = mocker.patch(
            "warehouse.organizations.tasks."
            "send_organization_subscription_required_email",
        )

        organization = OrganizationFactory.create(
            orgtype=OrganizationType.Company, is_active=True
        )
        owner1 = UserFactory.create()
        owner2 = UserFactory.create()
        OrganizationRoleFactory.create(
            organization=organization, user=owner1, role_name=OrganizationRoleType.Owner
        )
        OrganizationRoleFactory.create(
            organization=organization, user=owner2, role_name=OrganizationRoleType.Owner
        )
        # A non-owner member should not be notified.
        OrganizationRoleFactory.create(
            organization=organization,
            user=UserFactory.create(),
            role_name=OrganizationRoleType.Member,
        )

        notify_organizations_requiring_subscription(db_request)

        assert send_email.call_count == 2
        send_email.assert_any_call(
            db_request, owner1, organization_name=organization.name
        )
        send_email.assert_any_call(
            db_request, owner2, organization_name=organization.name
        )

    def test_skips_good_standing_non_company_and_inactive_orgs(
        self, db_request, mocker
    ):
        send_email = mocker.patch(
            "warehouse.organizations.tasks."
            "send_organization_subscription_required_email",
        )

        # Company org in good standing via an active manual activation.
        good_standing = OrganizationFactory.create(
            orgtype=OrganizationType.Company, is_active=True
        )
        OrganizationManualActivationFactory.create(organization=good_standing)
        OrganizationRoleFactory.create(
            organization=good_standing,
            user=UserFactory.create(),
            role_name=OrganizationRoleType.Owner,
        )

        # Community org (only Company orgs require a subscription).
        community = OrganizationFactory.create(
            orgtype=OrganizationType.Community, is_active=True
        )
        OrganizationRoleFactory.create(
            organization=community,
            user=UserFactory.create(),
            role_name=OrganizationRoleType.Owner,
        )

        # Inactive Company org.
        inactive = OrganizationFactory.create(
            orgtype=OrganizationType.Company, is_active=False
        )
        OrganizationRoleFactory.create(
            organization=inactive,
            user=UserFactory.create(),
            role_name=OrganizationRoleType.Owner,
        )

        notify_organizations_requiring_subscription(db_request)

        send_email.assert_not_called()

    def test_skips_recently_approved_orgs_within_grace_period(self, db_request, mocker):
        send_email = mocker.patch(
            "warehouse.organizations.tasks."
            "send_organization_subscription_required_email",
        )

        organization = OrganizationFactory.create(
            orgtype=OrganizationType.Company,
            is_active=True,
            created=datetime.datetime.now(datetime.UTC),
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=UserFactory.create(),
            role_name=OrganizationRoleType.Owner,
        )

        notify_organizations_requiring_subscription(db_request)

        send_email.assert_not_called()

    def test_handles_company_org_without_owners(self, db_request, mocker):
        send_email = mocker.patch(
            "warehouse.organizations.tasks."
            "send_organization_subscription_required_email",
        )

        OrganizationFactory.create(orgtype=OrganizationType.Company, is_active=True)

        notify_organizations_requiring_subscription(db_request)

        send_email.assert_not_called()
