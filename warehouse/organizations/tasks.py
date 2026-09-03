# SPDX-License-Identifier: Apache-2.0

import datetime

import stripe
import structlog

from sqlalchemy.orm import joinedload, selectinload

from warehouse import tasks, utils
from warehouse.accounts.interfaces import ITokenService, TokenExpired
from warehouse.email import (
    send_organization_deactivated_email,
    send_organization_subscription_required_email,
)
from warehouse.events.tags import EventTag
from warehouse.metrics import IMetricsService
from warehouse.organizations.constants import (
    CLEANUP_AFTER,
    SUBSCRIPTION_GRACE_PERIOD,
    SUBSCRIPTION_NOTICE_AFTER,
)
from warehouse.organizations.models import (
    Organization,
    OrganizationApplication,
    OrganizationApplicationStatus,
    OrganizationInvitation,
    OrganizationInvitationStatus,
    OrganizationManualActivation,
    OrganizationStripeSubscription,
    OrganizationType,
)
from warehouse.subscriptions.interfaces import IBillingService
from warehouse.subscriptions.models import (
    ACTIVE_SUBSCRIPTION_STATUSES,
    StripeSubscription,
    StripeSubscriptionStatus,
)

logger = structlog.get_logger(__name__)


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

    billing_service = request.find_service(IBillingService, context=None)
    metrics = request.find_service(IMetricsService, context=None)

    # Call the Billing API to update the usage record of this subscription item
    for org_subscription in organization_subscriptions:
        if org_subscription.subscription.status == StripeSubscriptionStatus.Canceled:
            continue
        try:
            billing_service.create_or_update_usage_record(
                org_subscription.subscription.subscription_item.subscription_item_id,
                len(org_subscription.organization.users),
            )
        except stripe.error.StripeError as exc:
            # Isolate per-subscription failures so one (e.g. canceled on Stripe with a
            # stale local status) can't abort usage reporting for every other org.
            logger.exception(
                "Failed to update usage record",
                organization_name=org_subscription.organization.name,
                subscription_id=org_subscription.subscription.subscription_id,
            )
            metrics.increment(
                "warehouse.organizations.subscription.usage_record.error",
                tags=[f"error_type:{exc.__class__.__name__}"],
            )
        else:
            metrics.increment(
                "warehouse.organizations.subscription.usage_record.updated"
            )


@tasks.task(ignore_result=True, acks_late=True)
def notify_organizations_requiring_subscription(request):
    """
    Email owners of company orgs that have no active subscription
    (or manual activation) that 1 seat is required for paid orgs.

    Orgs get 30 days (SUBSCRIPTION_GRACE_PERIOD) from creation to activate a
    subscription before ``deactivate_organizations_requiring_subscription``
    deactivates them, so reminders start at SUBSCRIPTION_NOTICE_AFTER -- while
    the owners can still act on them.
    """
    organizations = (
        request.db.query(Organization)
        .filter(
            Organization.is_active.is_(True),
            Organization.orgtype == OrganizationType.Company,
            Organization.created
            < (datetime.datetime.now(datetime.UTC) - SUBSCRIPTION_NOTICE_AFTER),
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


@tasks.task(ignore_result=True, acks_late=True)
def deactivate_organizations_requiring_subscription(request):
    """
    Deactivate company orgs that have not activated a sub.

    Owners are sent notice when the organization is approved that a company
    organization needs at least one seat within SUBSCRIPTION_GRACE_PERIOD, and
    are reminded while that window is open by
    ``notify_organizations_requiring_subscription``.
    """
    # Naive UTC: the column compared below is a naive DateTime.
    now = utils.now()
    metrics = request.find_service(IMetricsService, context=None)

    organizations = (
        request.db.query(Organization)
        .filter(
            Organization.is_active.is_(True),
            Organization.orgtype == OrganizationType.Company,
            Organization.created < (now - SUBSCRIPTION_GRACE_PERIOD),
            # No active orgs + No orgs manually activaed that
            # is still active
            ~Organization.subscriptions.any(
                StripeSubscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES)
            ),
            ~Organization.manual_activation.has(
                OrganizationManualActivation.expires > datetime.date.today()
            ),
        )
        .options(
            selectinload(Organization.subscriptions),
            joinedload(Organization.manual_activation),
        )
        .all()
    )

    # find all orgs not in good standing and deactivate + log + email
    for organization in organizations:
        # just in case
        if organization.is_in_good_standing():
            continue

        organization.is_active = False
        organization.record_event(
            tag=EventTag.Organization.OrganizationDeactivate,
            request=request,
            additional={"reason": "subscription_required"},
        )
        metrics.increment("warehouse.organizations.subscription.deactivated")

        for owner in organization.owners:
            if owner.primary_email is None or not owner.primary_email.verified:
                continue
            send_organization_deactivated_email(
                request,
                owner,
                organization_name=organization.name,
            )
