# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import datetime as dt
import typing

from collections import defaultdict
from uuid import UUID

import stripe
import structlog

from pyramid_retry import RetryableException
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import joinedload, selectinload

from warehouse import tasks
from warehouse.accounts.interfaces import (
    ITokenService,
    IUserService,
    TokenException,
    TokenExpired,
)
from warehouse.accounts.models import Email, User
from warehouse.admin.flags import AdminFlagValue
from warehouse.email import (
    send_organization_deactivated_email,
    send_organization_subscription_required_email,
)
from warehouse.events.tags import EventTag
from warehouse.observations.models import ObservationKind
from warehouse.organizations.constants import (
    CLEANUP_AFTER,
    DEACTIVATION_NOTICE_DAYS,
    DEACTIVATION_STARTS_PER_DAY,
    DEACTIVATIONS_PER_DAY,
    RECONCILE_MAX_DOWNGRADES,
    SUBSCRIPTION_NOTICE_AFTER,
    UNDEFER_AFTER,
)
from warehouse.organizations.models import (
    Organization,
    OrganizationApplication,
    OrganizationApplicationStatus,
    OrganizationDeactivationNotice,
    OrganizationDeactivationReason,
    OrganizationDeactivationSchedule,
    OrganizationInvitation,
    OrganizationInvitationStatus,
    OrganizationNameCatalog,
    OrganizationRole,
    OrganizationRoleType,
    OrganizationStripeSubscription,
    OrganizationType,
)
from warehouse.subscriptions.interfaces import IBillingService, ISubscriptionService
from warehouse.subscriptions.models import (
    ACTIVE_SUBSCRIPTION_STATUSES,
    StripeSubscription,
    StripeSubscriptionStatus,
)

if typing.TYPE_CHECKING:
    from pyramid.request import Request

TRANSIENT_STRIPE_ERRORS = (
    stripe.error.APIConnectionError,
    stripe.error.APIError,
    stripe.error.RateLimitError,
)
UNPAID_SUBSCRIPTION_STATUSES = frozenset(
    status.value
    for status in StripeSubscriptionStatus
    if status.value not in ACTIVE_SUBSCRIPTION_STATUSES
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
        except TokenException:
            logger.warning(
                "Skipping organization invitation with an unreadable token",
                invitation_id=str(invite.id),
            )


@tasks.task(ignore_result=True, acks_late=True)
def delete_declined_organization_applications(request):
    organization_applications = (
        request.db.query(OrganizationApplication)
        .filter(
            OrganizationApplication.status.in_(
                (
                    OrganizationApplicationStatus.Declined,
                    OrganizationApplicationStatus.Withdrawn,
                )
            ),
            OrganizationApplication.updated < (dt.datetime.now(dt.UTC) - CLEANUP_AFTER),
        )
        .all()
    )

    for organization_application in organization_applications:
        request.db.delete(organization_application)


@tasks.task(ignore_result=True, acks_late=True)
def undefer_organization_applications(request: Request) -> None:
    """Return applications deferred for `UNDEFER_AFTER` to the review queue."""
    organization_applications = (
        request.db.query(OrganizationApplication)
        .filter(
            OrganizationApplication.status == OrganizationApplicationStatus.Deferred,
            OrganizationApplication.updated < (dt.datetime.now(dt.UTC) - UNDEFER_AFTER),
            # A name another organization now holds can't be approved; leave it.
            ~exists().where(
                OrganizationNameCatalog.normalized_name
                == OrganizationApplication.normalized_name,
                OrganizationNameCatalog.organization_id.is_not(None),
            ),
        )
        # Lock so a concurrent approve, decline or withdraw isn't overwritten.
        .with_for_update(skip_locked=True)
        .all()
    )
    if not organization_applications:
        return

    admin = request.find_service(IUserService).get_admin_user()
    message = f"Returned to review after {UNDEFER_AFTER.days} days deferred."
    for organization_application in organization_applications:
        organization_application.status = OrganizationApplicationStatus.Submitted
        organization_application.record_observation(
            request=request,
            actor=admin,
            summary="Admin note added",
            kind=ObservationKind.AdminNote,
            payload={"message": message},
        )


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

    # Webhooks normally apply these first, so a run that takes many subscriptions
    # off a paid status points at a bug or a bad Stripe response. Each one would
    # start a deactivation notice period, so hold them all and apply the rest.
    # Held subscriptions keep their paid status and are checked again next run.
    downgrades = {
        org_subscription.subscription.id
        for org_subscription in organization_subscriptions
        if org_subscription.subscription.status in ACTIVE_SUBSCRIPTION_STATUSES
        and remote_statuses.get(org_subscription.subscription.subscription_id)
        in UNPAID_SUBSCRIPTION_STATUSES
    }
    held = downgrades if len(downgrades) > RECONCILE_MAX_DOWNGRADES else set()
    if held:
        logger.error(
            "Holding subscription downgrades over the limit",
            downgrades=len(held),
            limit=RECONCILE_MAX_DOWNGRADES,
        )
        request.metrics.increment(
            "warehouse.organizations.subscription.status.reconcile.held",
            len(held),
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

        if subscription.id in held:
            continue

        if not subscription_service.sync_subscription_status(
            subscription.id, remote_status, request=request
        ):
            continue

        request.metrics.increment(
            "warehouse.organizations.subscription.status.reconciled",
            tags=[f"status:{remote_status}"],
        )


def _reachable_owners(organization: Organization) -> list[tuple[User, Email]]:
    """Each owner with a verified address: their primary, else any other verified."""
    reachable = []
    for owner in organization.owners:
        verified = sorted(
            (email for email in owner.emails if email.verified),
            key=lambda email: (not email.primary, email.id),
        )
        if verified:
            reachable.append((owner, verified[0]))
    return reachable


def _queue_reminder(
    request: Request, schedule: OrganizationDeactivationSchedule
) -> None:
    request.db.add(
        OrganizationDeactivationNotice(
            organization=schedule.organization, deactivated=False
        )
    )
    request.metrics.increment(
        "warehouse.organizations.deactivation.notice",
        tags=[f"days:{schedule.last_notice_days}"],
    )


def _stripe_skip_reason(request: Request, organization: Organization) -> str | None:
    """Why Stripe says not to deactivate, or None if it agrees the org is unpaid."""
    billing_service = request.find_service(IBillingService, context=None)
    try:
        paid_on_stripe = any(
            remote["status"] in ACTIVE_SUBSCRIPTION_STATUSES
            for remote in billing_service.list_customer_subscriptions(
                organization.customer.customer_id
            )
        )
    except stripe.error.StripeError:
        # Raising would roll back the whole run, so only this org waits a night.
        logger.exception(
            "Failed to check Stripe before deactivation",
            organization_name=organization.name,
        )
        return "stripe_error"
    if paid_on_stripe:
        logger.error(
            "Stored status lacks a paid seat, but Stripe has one",
            organization_name=organization.name,
        )
        return "paid_on_stripe"
    return None


@tasks.task(ignore_result=True, acks_late=True)
def schedule_unpaid_organization_deactivations(request: Request) -> None:
    """Daily: process scheduled orgs and capped new starts, then dispatch notices."""
    if request.flags.enabled(AdminFlagValue.DISALLOW_ORGANIZATION_DEACTIVATION):
        return

    # Oldest deadline first, so a capped night defers the most recent ones.
    scheduled = request.db.scalars(
        select(OrganizationDeactivationSchedule.organization_id).order_by(
            OrganizationDeactivationSchedule.deactivate_on,
            OrganizationDeactivationSchedule.created,
        )
    ).all()

    candidates = (
        request.db.query(Organization)
        .filter(
            ~Organization.deactivation_schedule.has(),
            Organization.is_active.is_(True),
            Organization.orgtype == OrganizationType.Company,
            Organization.created
            < (dt.datetime.now(dt.UTC) - SUBSCRIPTION_NOTICE_AFTER),
            # Unreachable orgs that own projects are skipped, so don't spend the cap.
            or_(
                Organization.roles.any(
                    and_(
                        OrganizationRole.role_name == OrganizationRoleType.Owner,
                        OrganizationRole.user.has(
                            User.emails.any(Email.verified.is_(True))
                        ),
                    )
                ),
                ~Organization.projects.any(),
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

    # One transaction keeps the owner's batch complete even if processing is slow.
    # Any failure rolls back every change; organization locks last until commit.
    deactivations = 0
    for organization_id in [*scheduled, *unpaid[:DEACTIVATION_STARTS_PER_DAY]]:
        if deactivate_unpaid_organization(
            request,
            organization_id,
            may_deactivate=deactivations < DEACTIVATIONS_PER_DAY,
        ):
            deactivations += 1

    # WarehouseTask dispatches only after all schedules and notices have committed.
    request.task(send_organization_deactivation_notices).delay()


def deactivate_unpaid_organization(
    request: Request, organization_id: UUID, *, may_deactivate: bool = True
) -> bool:
    """Queue the next notice for one org, deactivate it, or clear its schedule.

    Returns whether it deactivated the org.
    """
    if request.flags.enabled(AdminFlagValue.DISALLOW_ORGANIZATION_DEACTIVATION):
        return False

    # Lock so a duplicate producer can't queue the same notice twice.
    organization = request.db.get(Organization, organization_id, with_for_update=True)
    if organization is None:
        return False

    schedule = organization.deactivation_schedule
    if not organization.lacks_paid_seat:
        if schedule is not None:
            request.db.delete(schedule)
            request.metrics.increment("warehouse.organizations.deactivation.cleared")
        return False

    # Nobody to warn: only deactivate if no project uploads would break.
    if not _reachable_owners(organization) and organization.projects:
        if schedule is not None:
            request.db.delete(schedule)
        request.metrics.increment(
            "warehouse.organizations.deactivation.skipped",
            tags=["reason:no_recipients"],
        )
        return False

    today = dt.datetime.now(dt.UTC).date()

    if schedule is None:
        notice_days = DEACTIVATION_NOTICE_DAYS[0]
        schedule = OrganizationDeactivationSchedule(
            organization=organization,
            deactivate_on=today + dt.timedelta(days=notice_days),
            last_notice_days=notice_days,
        )
        request.db.add(schedule)
        _queue_reminder(request, schedule)
        return False

    days_remaining = (schedule.deactivate_on - today).days
    due = [
        days
        for days in DEACTIVATION_NOTICE_DAYS
        if days_remaining <= days < schedule.last_notice_days
    ]
    if due:
        # A late reminder still gives its full days; several missed restarts at 30.
        notice_days = due[0] if len(due) == 1 else DEACTIVATION_NOTICE_DAYS[0]
        schedule.deactivate_on = today + dt.timedelta(days=notice_days)
        schedule.last_notice_days = notice_days
        _queue_reminder(request, schedule)
        return False

    # Owners have all of deactivate_on (UTC) to purchase a seat.
    if days_remaining >= 0:
        return False

    # A pause or missed runs can make many deadlines fall on one night. Keep the
    # schedule so the org is deactivated on a later night instead.
    if not may_deactivate:
        request.metrics.increment("warehouse.organizations.deactivation.deferred")
        return False

    # The stored status can be wrong (a lost webhook, a reconciliation bug), so
    # ask Stripe before the one step owners can't undo themselves. Keep the
    # schedule, so the next run asks again.
    if organization.customer is not None:
        skip_reason = _stripe_skip_reason(request, organization)
        if skip_reason is not None:
            request.metrics.increment(
                "warehouse.organizations.deactivation.skipped",
                tags=[f"reason:{skip_reason}"],
            )
            return False

    organization.deactivate(OrganizationDeactivationReason.NoPaidSeat)
    organization.record_event(
        tag=EventTag.Organization.OrganizationDeactivate,
        request=request,
        additional={"reason": OrganizationDeactivationReason.NoPaidSeat.value},
    )
    request.db.delete(schedule)
    request.db.add(
        OrganizationDeactivationNotice(organization=organization, deactivated=True)
    )
    request.metrics.increment("warehouse.organizations.deactivation.deactivated")
    return True


@tasks.task(ignore_result=True, acks_late=True)
def send_organization_deactivation_notices(request: Request) -> None:
    """After the producer commits, email each owner one batch of queued notices."""
    if request.flags.enabled(AdminFlagValue.DISALLOW_ORGANIZATION_DEACTIVATION):
        return

    # skip_locked: another run is already sending these.
    notices = request.db.scalars(
        select(OrganizationDeactivationNotice)
        .options(selectinload(OrganizationDeactivationNotice.organization))
        .with_for_update(skip_locked=True)
    ).all()

    # Drop notices the org no longer needs, e.g. it paid since they were queued.
    reminders: dict[tuple[User, Email], set[OrganizationDeactivationSchedule]] = (
        defaultdict(set)
    )
    deactivations: dict[tuple[User, Email], dict[str, dt.date]] = defaultdict(dict)
    for notice in notices:
        organization = notice.organization
        schedule = organization.deactivation_schedule
        deadline = organization.reactivation_deadline
        if not notice.deactivated and organization.lacks_paid_seat and schedule:
            for recipient in _reachable_owners(organization):
                reminders[recipient].add(schedule)
        elif notice.deactivated and organization.reactivates_on_payment and deadline:
            for recipient in _reachable_owners(organization):
                deactivations[recipient][organization.name] = deadline
        request.db.delete(notice)

    today = dt.datetime.now(dt.UTC).date()
    for recipient, schedules in reminders.items():
        send_organization_subscription_required_email(
            request,
            recipient,
            organizations=[
                {
                    "name": schedule.organization.name,
                    "deactivate_on": schedule.deactivate_on,
                    "days_remaining": (schedule.deactivate_on - today).days,
                }
                for schedule in sorted(
                    schedules, key=lambda s: (s.deactivate_on, s.organization.name)
                )
            ],
        )
    for recipient, deadlines in deactivations.items():
        send_organization_deactivated_email(
            request,
            recipient,
            organizations=[
                {"name": name, "reactivate_by": reactivate_by}
                for name, reactivate_by in sorted(deadlines.items())
            ],
        )
