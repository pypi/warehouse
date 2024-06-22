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

from warehouse import tasks
from warehouse.accounts.interfaces import ITokenService, TokenExpired
from warehouse.events.tags import EventTag
from warehouse.organizations.interfaces import IOrganizationService
from warehouse.organizations.models import (
    Organization,
    OrganizationInvitation,
    OrganizationInvitationStatus,
    OrganizationStripeSubscription,
)
from warehouse.subscriptions.interfaces import IBillingService

CLEANUP_AFTER = datetime.timedelta(days=30)


@tasks.task(ignore_result=True, acks_late=True)
def update_organization_invitation_status(request):
    invites = (
        request.db.query(OrganizationInvitation)
        .filter(
            OrganizationInvitation.invite_status == OrganizationInvitationStatus.Pending
        )
        .all()
    )
    token_service = request.find_service(ITokenService, name="email")

    for invite in invites:
        try:
            token_service.loads(invite.token)
        except TokenExpired:
            invite.user.record_event(
                tag=EventTag.Account.OrganizationRoleExpireInvite,
                request=request,
                additional={
                    "organization_name": invite.organization.name,
                },
            )
            invite.organization.record_event(
                tag=EventTag.Organization.OrganizationRoleExpireInvite,
                request=request,
                additional={
                    "target_user_id": str(invite.user.id),
                },
            )
            invite.invite_status = OrganizationInvitationStatus.Expired


@tasks.task(ignore_result=True, acks_late=True)
def delete_declined_organizations(request):
    organizations = (
        request.db.query(Organization)
        .filter(
            Organization.is_active == False,  # noqa: E712
            Organization.is_approved == False,  # noqa: E712
            Organization.date_approved
            < (datetime.datetime.now(datetime.UTC) - CLEANUP_AFTER),
        )
        .all()
    )

    for organization in organizations:
        organization_service = request.find_service(IOrganizationService, context=None)
        # TODO: Cannot call this after deletion so how exactly do we handle this?
        organization.record_event(
            tag=EventTag.Organization.OrganizationDelete,
            request=request,
            additional={"deleted_by": "CRON"},
        )
        organization_service.delete_organization(organization.id)


@tasks.task(ignore_result=True, acks_late=True)
def update_organziation_subscription_usage_record(request):
    # Get organizations with a subscription
    organization_subscriptions = request.db.query(OrganizationStripeSubscription).all()

    # Call the Billing API to update the usage record of this subscription item
    for org_subscription in organization_subscriptions:
        billing_service = request.find_service(IBillingService, context=None)
        billing_service.create_or_update_usage_record(
            org_subscription.subscription.subscription_item.subscription_item_id,
            len(org_subscription.organization.users),
        )
