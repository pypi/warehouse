# SPDX-License-Identifier: Apache-2.0

import datetime

from sqlalchemy.orm import joinedload

from warehouse import tasks
from warehouse.accounts.interfaces import ITokenService, TokenExpired
from warehouse.email import send_organization_subscription_required_email
from warehouse.events.tags import EventTag
from warehouse.organizations.models import (
    Organization,
    OrganizationApplication,
    OrganizationApplicationStatus,
    OrganizationInvitation,
    OrganizationInvitationStatus,
    OrganizationStripeSubscription,
    OrganizationType,
)
from warehouse.subscriptions.interfaces import IBillingService
from warehouse.subscriptions.models import StripeSubscriptionStatus

CLEANUP_AFTER = datetime.timedelta(days=30)
SUBSCRIPTION_GRACE_PERIOD = datetime.timedelta(days=30)


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
        if org_subscription.subscription.status != StripeSubscriptionStatus.Canceled:
            billing_service = request.find_service(IBillingService, context=None)
            billing_service.create_or_update_usage_record(
                org_subscription.subscription.subscription_item.subscription_item_id,
                len(org_subscription.organization.users),
            )


@tasks.task(ignore_result=True, acks_late=True)
def notify_organizations_requiring_subscription(request):
    """
    Email owners of company orgs that have no active subscription
    (or manual activation) that 1 seat is required for paid orgs.

    Orgs get 30 days (SUBSCRIPTION_GRACE_PERIOD) to activate a subscription before they are considered not in good standing.
    """
    organizations = (
        request.db.query(Organization)
        .filter(
            Organization.is_active.is_(True),
            Organization.orgtype == OrganizationType.Company,
            Organization.created
            < (datetime.datetime.now(datetime.UTC) - SUBSCRIPTION_GRACE_PERIOD),
        )
        .options(
            joinedload(Organization.subscriptions),
            joinedload(Organization.manual_activation),
        )
        .all()
    )

    for organization in organizations:
        if organization.is_in_good_standing():
            continue

        for user in organization.owners:
            send_organization_subscription_required_email(
                request,
                user,
                organization_name=organization.name,
            )
