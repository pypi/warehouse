# SPDX-License-Identifier: Apache-2.0

import datetime

from warehouse.accounts.interfaces import ITokenService, TokenExpired
from warehouse.events.tags import EventTag
from warehouse.organizations.models import (
    OrganizationApplication,
    OrganizationApplicationStatus,
    OrganizationInvitationStatus,
    OrganizationRoleType,
)
from warehouse.organizations.tasks import (
    delete_declined_organization_applications,
    update_organization_invitation_status,
    update_organziation_subscription_usage_record,
)
from warehouse.subscriptions.interfaces import IBillingService
from warehouse.subscriptions.models import StripeSubscriptionStatus

from ...common.db.organizations import (
    OrganizationApplicationFactory,
    OrganizationFactory,
    OrganizationInvitationFactory,
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

        mocker.patch.object(
            billing_service,
            "create_or_update_usage_record",
            return_value={
                "subscription_item_id": "si_1234",
                "organization_member_count": "5",
            },
        )
        find_service = mocker.spy(db_request, "find_service")

        update_organziation_subscription_usage_record(db_request)

        find_service.assert_called_once_with(IBillingService, context=None)
