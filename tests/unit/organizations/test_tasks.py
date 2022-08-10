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
from warehouse.organizations.models import (  # OrganizationRoleType,
    Organization,
    OrganizationInvitationStatus,
)
from warehouse.organizations.tasks import (  # update_organziation_subscription_usage_record,  # noqa
    delete_declined_organizations,
    update_organization_invitation_status,
)

from ...common.db.organizations import (  # OrganizationRoleFactory,; OrganizationStripeCustomerFactory,; OrganizationStripeSubscriptionFactory,  # noqa
    OrganizationFactory,
    OrganizationInvitationFactory,
    UserFactory,
)

# from ...common.db.subscriptions import (
#     StripeSubscriptionFactory,
#     StripeSubscriptionItemFactory,
#     StripeSubscriptionPriceFactory,
#     StripeSubscriptionProductFactory,
# )


class TestUpdateInvitationStatus:
    def test_update_invitation_status(self, db_request):
        organization = OrganizationFactory.create()
        user = UserFactory.create()
        invite = OrganizationInvitationFactory(user=user, organization=organization)

        token_service = pretend.stub(loads=pretend.raiser(TokenExpired))
        db_request.find_service = pretend.call_recorder(lambda *a, **kw: token_service)

        update_organization_invitation_status(db_request)

        assert db_request.find_service.calls == [
            pretend.call(ITokenService, name="email")
        ]
        assert invite.invite_status == OrganizationInvitationStatus.Expired

    def test_no_updates(self, db_request):
        organization = OrganizationFactory.create()
        user = UserFactory.create()
        invite = OrganizationInvitationFactory(user=user, organization=organization)

        token_service = pretend.stub(loads=lambda token: {})
        db_request.find_service = pretend.call_recorder(lambda *a, **kw: token_service)

        update_organization_invitation_status(db_request)

        assert db_request.find_service.calls == [
            pretend.call(ITokenService, name="email")
        ]
        assert invite.invite_status == OrganizationInvitationStatus.Pending


class TestDeleteOrganizations:
    def test_delete_declined_organizations(self, db_request):
        # Create an organization that's ready for cleanup
        organization = OrganizationFactory.create()
        organization.is_active = False
        organization.is_approved = False
        organization.date_approved = datetime.datetime.now() - datetime.timedelta(
            days=31
        )

        # Create an organization that's not ready to be cleaned up yet
        organization2 = OrganizationFactory.create()
        organization2.is_active = False
        organization2.is_approved = False
        organization2.date_approved = datetime.datetime.now()

        assert (
            db_request.db.query(Organization.id)
            .filter(Organization.id == organization.id)
            .count()
            == 1
        )

        assert (
            db_request.db.query(Organization.id)
            .filter(Organization.id == organization2.id)
            .count()
            == 1
        )

        assert db_request.db.query(Organization).count() == 2

        delete_declined_organizations(db_request)

        assert not (
            (
                db_request.db.query(Organization.id)
                .filter(Organization.id == organization.id)
                .count()
            )
        )

        assert (
            db_request.db.query(Organization.id)
            .filter(Organization.id == organization2.id)
            .count()
        )

        assert db_request.db.query(Organization).count() == 1


# TODO: Get this test working
# class TestUpdateOrganizationSubscriptionUsage:
#     def test_update_organziation_subscription_usage_record(self, db_request):
#         # Create an organization with a subscription and members
#         organization = OrganizationFactory.create()
#         # Add a couple members
#         owner_user = UserFactory.create()
#         OrganizationRoleFactory(
#             organization=organization,
#             user=owner_user,
#             role_name=OrganizationRoleType.Owner,
#         )
#         member_user = UserFactory.create()
#         OrganizationRoleFactory(
#             organization=organization,
#             user=member_user,
#             role_name=OrganizationRoleType.Member,
#         )
#         # Wire up the customer, subscripton, organization, and subscription item
#         organization_stripe_customer = OrganizationStripeCustomerFactory.create(
#             organization=organization
#         )
#         subscription_product = StripeSubscriptionProductFactory.create()
#         subscription_price = StripeSubscriptionPriceFactory.create(
#             subscription_product=subscription_product
#         )
#         subscription = StripeSubscriptionFactory.create(
#             customer_id=organization_stripe_customer.customer_id,
#             subscription_price=subscription_price,
#         )
#         OrganizationStripeSubscriptionFactory.create(
#             organization=organization, subscription=subscription
#         )
#         StripeSubscriptionItemFactory.create(
#             subscription=subscription, subscription_price=subscription_price
#         )

#         result = update_organziation_subscription_usage_record(db_request)

#         # TODO: This is silly, need to figure out what I should actually be checking for  # noqa
#         assert isinstance(result, None)
