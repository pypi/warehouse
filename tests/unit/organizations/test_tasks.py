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

import pretend

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
        self, db_request, user_service, organization_service
    ):
        organization = OrganizationFactory.create()
        organization.record_event = pretend.call_recorder(lambda *a, **kw: None)
        user = UserFactory.create()
        user.record_event = pretend.call_recorder(lambda *a, **kw: None)

        invite = OrganizationInvitationFactory(user=user, organization=organization)

        token_service = pretend.stub(loads=pretend.raiser(TokenExpired))
        db_request.find_service = pretend.call_recorder(lambda *a, **kw: token_service)

        update_organization_invitation_status(db_request)

        assert db_request.find_service.calls == [
            pretend.call(ITokenService, name="email")
        ]
        assert invite.invite_status == OrganizationInvitationStatus.Expired

        assert user.record_event.calls == [
            pretend.call(
                tag=EventTag.Account.OrganizationRoleExpireInvite,
                request=db_request,
                additional={"organization_name": invite.organization.name},
            )
        ]
        assert organization.record_event.calls == [
            pretend.call(
                tag=EventTag.Organization.OrganizationRoleExpireInvite,
                request=db_request,
                additional={"target_user_id": str(invite.user.id)},
            )
        ]

    def test_no_updates(self, db_request, user_service, organization_service):
        organization = OrganizationFactory.create()
        organization.record_event = pretend.call_recorder(lambda *a, **kw: None)
        user = UserFactory.create()
        user.record_event = pretend.call_recorder(lambda *a, **kw: None)

        invite = OrganizationInvitationFactory(user=user, organization=organization)

        token_service = pretend.stub(loads=lambda token: {})
        db_request.find_service = pretend.call_recorder(lambda *a, **kw: token_service)

        update_organization_invitation_status(db_request)

        assert db_request.find_service.calls == [
            pretend.call(ITokenService, name="email")
        ]
        assert invite.invite_status == OrganizationInvitationStatus.Pending

        assert user.record_event.calls == []
        assert organization.record_event.calls == []


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
    def test_update_organization_subscription_usage_record(self, db_request):
        # Create an organization with a subscription and members
        organization = OrganizationFactory.create()
        # Add a couple members
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
        # Wire up the customer, subscripton, organization, and subscription item
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

        create_or_update_usage_record = pretend.call_recorder(
            lambda *a, **kw: {
                "subscription_item_id": "si_1234",
                "organization_member_count": "5",
            }
        )
        billing_service = pretend.stub(
            create_or_update_usage_record=create_or_update_usage_record,
        )

        db_request.find_service = pretend.call_recorder(
            lambda *a, **kw: billing_service
        )

        update_organziation_subscription_usage_record(db_request)

        assert db_request.find_service.calls == [
            pretend.call(IBillingService, context=None)
        ]
