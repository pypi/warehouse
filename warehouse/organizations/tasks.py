# SPDX-License-Identifier: Apache-2.0

import datetime
import logging

import stripe

from pyramid_retry import RetryableException
from sqlalchemy.orm import joinedload

from warehouse import tasks
from warehouse.accounts.interfaces import ITokenService, TokenExpired
from warehouse.email import send_organization_subscription_required_email
from warehouse.events.tags import EventTag
from warehouse.metrics import IMetricsService
from warehouse.organizations.models import (
    Organization,
    OrganizationApplication,
    OrganizationApplicationStatus,
    OrganizationInvitation,
    OrganizationInvitationStatus,
    OrganizationStripeSubscription,
    OrganizationType,
)
from warehouse.subscriptions.interfaces import IBillingService, ISubscriptionService
from warehouse.subscriptions.models import StripeSubscriptionStatus
from warehouse.subscriptions.services import TRANSIENT_STRIPE_ERRORS

CLEANUP_AFTER = datetime.timedelta(days=30)
SUBSCRIPTION_GRACE_PERIOD = datetime.timedelta(days=30)

logger = logging.getLogger(__name__)


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
        except TRANSIENT_STRIPE_ERRORS as exc:
            # Abort and retry the whole run rather than silently reporting no
            # usage for everyone.
            raise RetryableException from exc
        except stripe.error.InvalidRequestError as exc:
            # Skip a single bad subscription (e.g. canceled on Stripe, stale
            # locally).
            logger.exception(
                "Failed to update usage record for organization %r (subscription %s)",
                org_subscription.organization.name,
                org_subscription.subscription.subscription_id,
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
def reconcile_stripe_status(request):
    # Re-sync each subscription's status from Stripe so that state we would have
    # learned from a webhook (e.g. a cancellation) is recovered even if the
    # webhook was dropped. Mirrors the customer.subscription.updated handler.
    organization_subscriptions = request.db.query(OrganizationStripeSubscription).all()

    billing_service = request.find_service(IBillingService, context=None)
    subscription_service = request.find_service(ISubscriptionService, context=None)
    metrics = request.find_service(IMetricsService, context=None)

    for org_subscription in organization_subscriptions:
        subscription = org_subscription.subscription
        try:
            remote = billing_service.retrieve_subscription(subscription.subscription_id)
        except TRANSIENT_STRIPE_ERRORS as exc:
            raise RetryableException from exc
        deleted = remote is None
        remote_status = (
            StripeSubscriptionStatus.Canceled.value if deleted else remote["status"]
        )

        if not StripeSubscriptionStatus.has_value(remote_status):
            logger.warning(
                "Skipping subscription %s with unknown Stripe status %r",
                subscription.subscription_id,
                remote_status,
            )
            metrics.increment(
                "warehouse.organizations.subscription.status.reconcile.skipped"
            )
            continue

        previous_status = subscription.status
        if previous_status == remote_status:
            continue

        subscription_service.update_subscription_status(subscription.id, remote_status)
        if deleted:
            # Mirror the customer.subscription.deleted handler.
            org_subscription.organization.record_event(
                tag=EventTag.Organization.SubscriptionCancel,
                request=request,
                additional={"subscription_id": subscription.subscription_id},
            )
        else:
            org_subscription.organization.record_event(
                tag=EventTag.Organization.SubscriptionStatusChange,
                request=request,
                additional={
                    "subscription_id": subscription.subscription_id,
                    "previous_status": previous_status,
                    "status": remote_status,
                },
            )
        metrics.increment(
            "warehouse.organizations.subscription.status.reconciled",
            tags=[f"status:{remote_status}"],
        )


@tasks.task(ignore_result=True, acks_late=True)
def notify_organizations_requiring_subscription(request):
    """
    Email owners of company orgs that have no active subscription
    (or manual activation) that 1 seat is required for paid orgs.

    Orgs get 30 days (SUBSCRIPTION_GRACE_PERIOD) to activate a subscription
    before they are considered not in good standing.
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
