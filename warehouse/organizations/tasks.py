# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import datetime
import typing

from collections import defaultdict
from uuid import UUID

import stripe
import structlog

from pyramid_retry import RetryableException
from sqlalchemy import and_, select
from sqlalchemy.orm import joinedload, selectinload

from warehouse import tasks
from warehouse.accounts.interfaces import ITokenService, TokenExpired
from warehouse.accounts.models import Email, User
from warehouse.admin.flags import AdminFlagValue
from warehouse.email import (
    send_organization_deactivated_email,
    send_organization_subscription_required_email,
)
from warehouse.events.tags import EventTag
from warehouse.organizations.constants import (
    CLEANUP_AFTER,
    DEACTIVATION_NOTICE_DAYS,
    DEACTIVATION_STARTS_PER_DAY,
    NO_PAID_SEAT_REASON,
    SUBSCRIPTION_NOTICE_AFTER,
)
from warehouse.organizations.models import (
    Organization,
    OrganizationApplication,
    OrganizationApplicationStatus,
    OrganizationDeactivationNotice,
    OrganizationDeactivationSchedule,
    OrganizationInvitation,
    OrganizationInvitationStatus,
    OrganizationRole,
    OrganizationRoleType,
    OrganizationStripeSubscription,
    OrganizationType,
)
from warehouse.subscriptions.interfaces import IBillingService, ISubscriptionService
from warehouse.subscriptions.models import StripeSubscription, StripeSubscriptionStatus

if typing.TYPE_CHECKING:
    from pyramid.request import Request

TRANSIENT_STRIPE_ERRORS = (
    stripe.error.APIConnectionError,
    stripe.error.APIError,
    stripe.error.RateLimitError,
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
        except stripe.error.StripeError as exc:
            # Skip a single bad subscription (e.g. canceled on Stripe, stale
            # locally) so one failure can't block usage reporting for the rest.
            logger.exception(
                "Failed to update usage record",
                organization_name=org_subscription.organization.name,
                subscription_id=org_subscription.subscription.subscription_id,
            )
            request.metrics.increment(
                "warehouse.organizations.subscription.usage_record.error",
                tags=[f"error_type:{exc.__class__.__name__}"],
            )
        else:
            request.metrics.increment(
                "warehouse.organizations.subscription.usage_record.updated"
            )


@tasks.task(ignore_result=True, acks_late=True)
def reconcile_stripe_status(request):
    # Re-sync each subscription's status from Stripe so that state we would have
    # learned from a webhook (e.g. a cancellation) is recovered even if the
    # webhook was dropped. Mirrors the customer.subscription.updated handler.
    # Canceled is terminal on Stripe, so those rows never need re-checking.
    organization_subscriptions = (
        request.db.query(OrganizationStripeSubscription)
        .join(OrganizationStripeSubscription.subscription)
        .filter(StripeSubscription.status != StripeSubscriptionStatus.Canceled)
        .all()
    )
    billing_service = request.find_service(IBillingService, context=None)
    subscription_service = request.find_service(ISubscriptionService, context=None)

    try:
        remote_statuses = {
            remote["id"]: remote["status"]
            for remote in billing_service.list_subscriptions()
        }
    except TRANSIENT_STRIPE_ERRORS as exc:
        raise RetryableException from exc

    # A key for the wrong Stripe account or mode matches none of our ids. Fail
    # loudly rather than skipping every row and reconciling nothing.
    if organization_subscriptions and not any(
        org_subscription.subscription.subscription_id in remote_statuses
        for org_subscription in organization_subscriptions
    ):
        raise RuntimeError(
            f"None of {len(organization_subscriptions)} subscriptions found on Stripe"
        )

    for org_subscription in organization_subscriptions:
        subscription = org_subscription.subscription
        remote_status = remote_statuses.get(subscription.subscription_id)
        if remote_status is None:
            logger.warning(
                "Skipping subscription with no record on Stripe",
                subscription_id=subscription.subscription_id,
            )
            request.metrics.increment(
                "warehouse.organizations.subscription.status.reconcile.missing"
            )
            continue

        if not StripeSubscriptionStatus.has_value(remote_status):
            logger.warning(
                "Skipping subscription with unknown Stripe status",
                subscription_id=subscription.subscription_id,
                status=remote_status,
            )
            request.metrics.increment(
                "warehouse.organizations.subscription.status.reconcile.skipped",
                tags=[f"remote_status:{remote_status}"],
            )
            continue

        if not subscription_service.sync_subscription_status(
            subscription.id, remote_status, request=request
        ):
            continue

        request.metrics.increment(
            "warehouse.organizations.subscription.status.reconciled",
            tags=[f"status:{remote_status}"],
        )


def _queue_reminder(
    request: Request,
    organization: Organization,
    schedule: OrganizationDeactivationSchedule,
) -> None:
    request.db.add(
        OrganizationDeactivationNotice(organization=organization, deactivated=False)
    )
    request.metrics.increment(
        "warehouse.organizations.deactivation.notice",
        tags=[f"days:{schedule.last_notice_days}"],
    )


@tasks.task(ignore_result=True, acks_late=True)
def schedule_unpaid_organization_deactivations(request: Request) -> None:
    """
    Daily: queue one deactivate_unpaid_organization task per org with a schedule,
    and for up to DEACTIVATION_STARTS_PER_DAY unpaid Company orgs without one,
    oldest first. New orgs get SUBSCRIPTION_NOTICE_AFTER first.
    """
    if request.flags.enabled(AdminFlagValue.DISALLOW_ORGANIZATION_DEACTIVATION):
        return

    scheduled = request.db.scalars(
        select(Organization.id).where(Organization.deactivation_schedule.has())
    ).all()

    candidates = (
        request.db.query(Organization)
        .filter(
            ~Organization.deactivation_schedule.has(),
            Organization.is_active.is_(True),
            Organization.orgtype == OrganizationType.Company,
            Organization.created
            < (datetime.datetime.now(datetime.UTC) - SUBSCRIPTION_NOTICE_AFTER),
            # Orgs nobody can be told about would take up the cap every night.
            Organization.roles.any(
                and_(
                    OrganizationRole.role_name == OrganizationRoleType.Owner,
                    OrganizationRole.user.has(
                        User.emails.any(
                            and_(Email.primary.is_(True), Email.verified.is_(True))
                        )
                    ),
                )
            ),
        )
        .options(
            joinedload(Organization.subscriptions),
            joinedload(Organization.manual_activation),
        )
        .order_by(Organization.created)
        .all()
    )
    unpaid = [org.id for org in candidates if org.lacks_paid_seat]

    for organization_id in [*scheduled, *unpaid[:DEACTIVATION_STARTS_PER_DAY]]:
        request.task(deactivate_unpaid_organization).delay(organization_id)


@tasks.task(ignore_result=True, acks_late=True)
def deactivate_unpaid_organization(request: Request, organization_id: UUID) -> None:
    """Queue the next notice for one org, deactivate it, or clear its schedule."""
    if request.flags.enabled(AdminFlagValue.DISALLOW_ORGANIZATION_DEACTIVATION):
        return

    # Lock the org so a duplicate task can't queue the same notice twice.
    organization = request.db.get(Organization, organization_id, with_for_update=True)
    if organization is None:
        return

    schedule = organization.deactivation_schedule
    if not organization.lacks_paid_seat:
        if schedule is not None:
            request.db.delete(schedule)
            request.metrics.increment("warehouse.organizations.deactivation.cleared")
        return

    today = datetime.datetime.now(datetime.UTC).date()
    owners = organization.owners

    if schedule is None:
        # Don't start the clock when there is nobody we can tell about it.
        if not any(
            owner.primary_email and owner.primary_email.verified for owner in owners
        ):
            request.metrics.increment(
                "warehouse.organizations.deactivation.skipped",
                tags=["reason:no_recipients"],
            )
            return
        notice_days = DEACTIVATION_NOTICE_DAYS[0]
        schedule = OrganizationDeactivationSchedule(
            organization=organization,
            deactivate_on=today + datetime.timedelta(days=notice_days),
            last_notice_days=notice_days,
        )
        request.db.add(schedule)
        _queue_reminder(request, organization, schedule)
        return

    days_remaining = (schedule.deactivate_on - today).days
    due = [
        days
        for days in DEACTIVATION_NOTICE_DAYS
        if days_remaining <= days < schedule.last_notice_days
    ]
    if due:
        # A late reminder moves the deadline out so it still gives that many days.
        # Missed a whole reminder (e.g. a long pause)? Start over at 30 days.
        notice_days = min(due) if len(due) == 1 else DEACTIVATION_NOTICE_DAYS[0]
        schedule.deactivate_on = max(
            schedule.deactivate_on, today + datetime.timedelta(days=notice_days)
        )
        schedule.last_notice_days = notice_days
        _queue_reminder(request, organization, schedule)
        return

    # Owners have until the end of deactivate_on (UTC) to purchase a seat.
    if days_remaining >= 0:
        return

    organization.is_active = False
    organization.record_event(
        tag=EventTag.Organization.OrganizationDeactivate,
        request=request,
        additional={"reason": NO_PAID_SEAT_REASON},
    )
    request.db.delete(schedule)
    request.db.add(
        OrganizationDeactivationNotice(organization=organization, deactivated=True)
    )
    request.metrics.increment("warehouse.organizations.deactivation.deactivated")


@tasks.task(ignore_result=True, acks_late=True)
def send_organization_deactivation_notices(request: Request) -> None:
    """Daily: email each owner one list of their orgs with queued notices."""
    if request.flags.enabled(AdminFlagValue.DISALLOW_ORGANIZATION_DEACTIVATION):
        return

    # Skip rows a concurrent run is already sending.
    notices = request.db.scalars(
        select(OrganizationDeactivationNotice)
        .options(selectinload(OrganizationDeactivationNotice.organization))
        .with_for_update(skip_locked=True)
    ).all()

    # Drop notices the org no longer needs, e.g. it paid since they were queued.
    owners: dict[UUID, User] = {}
    reminders: dict[UUID, set[OrganizationDeactivationSchedule]] = defaultdict(set)
    deactivations: dict[UUID, set[str]] = defaultdict(set)
    for notice in notices:
        organization = notice.organization
        schedule = organization.deactivation_schedule
        if notice.deactivated and not organization.is_active:
            for owner in organization.owners:
                owners[owner.id] = owner
                deactivations[owner.id].add(organization.name)
        elif not notice.deactivated and organization.lacks_paid_seat and schedule:
            for owner in organization.owners:
                owners[owner.id] = owner
                reminders[owner.id].add(schedule)
        request.db.delete(notice)

    today = datetime.datetime.now(datetime.UTC).date()
    for owner_id, owner in owners.items():
        if schedules := reminders[owner_id]:
            send_organization_subscription_required_email(
                request,
                owner,
                organizations=[
                    {
                        "name": schedule.organization.name,
                        "deactivate_on": schedule.deactivate_on,
                        "days_remaining": (schedule.deactivate_on - today).days,
                    }
                    for schedule in sorted(
                        schedules,
                        key=lambda s: (s.deactivate_on, s.organization.name),
                    )
                ],
            )
        if names := deactivations[owner_id]:
            send_organization_deactivated_email(
                request, owner, organization_names=sorted(names)
            )
