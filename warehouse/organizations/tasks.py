# SPDX-License-Identifier: Apache-2.0

import datetime

from warehouse import tasks
from warehouse.accounts.interfaces import ITokenService, TokenExpired
from warehouse.events.tags import EventTag
from warehouse.organizations.models import (
    OrganizationApplication,
    OrganizationApplicationStatus,
    OrganizationInvitation,
    OrganizationInvitationStatus,
    OrganizationStripeSubscription,
)
from warehouse.subscriptions.interfaces import IBillingService
from warehouse.subscriptions.models import StripeSubscriptionStatus

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
def delete_declined_organization_applications(request):
    organization_applications = (
        request.db.query(OrganizationApplication)
        .filter(
            OrganizationApplication.status == OrganizationApplicationStatus.Declined,
            OrganizationApplication.updated
            < (datetime.datetime.now(datetime.UTC) - CLEANUP_AFTER),
        )
        .all()
    )

    for organization_application in organization_applications:
        request.db.delete(organization_application)


@tasks.task(ignore_result=True, acks_late=True)
def update_organziation_subscription_usage_record(request):
    # Get organizations with a subscription
    organization_subscriptions = request.db.query(OrganizationStripeSubscription).all()

    # Call the Billing API to update the usage record of this subscription item
    for org_subscription in organization_subscriptions:
        if org_subscription.subscription.status not in (
            StripeSubscriptionStatus.Canceled,
        ):
            billing_service = request.find_service(IBillingService, context=None)
            billing_service.create_or_update_usage_record(
                org_subscription.subscription.subscription_item.subscription_item_id,
                len(org_subscription.organization.users),
            )
