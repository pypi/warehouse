# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import typing

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from warehouse import tasks
from warehouse.email import (
    send_pending_trusted_publisher_expiration_reminder_email,
    send_pending_trusted_publisher_expired_email,
)
from warehouse.events.tags import EventTag
from warehouse.macaroons.models import Macaroon
from warehouse.metrics import IMetricsService
from warehouse.oidc.models import OIDCPublisher, PendingOIDCPublisher
from warehouse.packaging.models import File, Project, Release

if typing.TYPE_CHECKING:
    from pyramid.request import Request

# Pending publishers expire after this many days.
PENDING_PUBLISHER_EXPIRY_DAYS = 30

# Pending publishers receive a reminder email this many days before expiry.
PENDING_PUBLISHER_REMINDER_DAYS = 5


def pending_publisher_cutoff(days: int) -> datetime:
    """Return the cutoff before which pending publishers older than `days` created.

    Returned as naive UTC to match the naive `created` column for in-Python comparisons.
    """
    return datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(days=days)


@tasks.task(ignore_result=True, acks_late=True)
def compute_oidc_metrics(request):
    metrics = request.find_service(IMetricsService, context=None)

    projects_configured_oidc = (
        request.db.query(Project.id).distinct().join(Project.oidc_publishers)
    )

    # Metric for count of all projects that have configured OIDC.
    metrics.gauge(
        "warehouse.oidc.total_projects_configured_oidc_publishers",
        projects_configured_oidc.count(),
    )

    # Need to check FileEvent.additional['publisher_url'] to determine which
    # projects have successfully published via an OIDC publisher.
    projects_published_with_oidc = (
        request.db.query(Project.id)
        .distinct()
        .join(Project.releases)
        .join(Release.files)
        .join(File.events)
        .where(File.Event.additional.op("->>")("publisher_url").is_not(None))
    )

    # Metric for count of all projects that have published via OIDC
    metrics.gauge(
        "warehouse.oidc.total_projects_published_with_oidc_publishers",
        projects_published_with_oidc.count(),
    )

    # Metric for total number of files published via OIDC
    metrics.gauge(
        "warehouse.oidc.total_files_published_with_oidc_publishers",
        request.db.query(File.Event)
        .where(File.Event.additional.op("->>")("publisher_url").is_not(None))
        .count(),
    )

    # Number of publishers for specific publishers
    for t in request.db.query(OIDCPublisher.discriminator).distinct().all():
        discriminator = t[0]
        metrics.gauge(
            "warehouse.oidc.publishers",
            request.db.query(OIDCPublisher)
            .where(OIDCPublisher.discriminator == discriminator)
            .count(),
            tags=[f"publisher:{discriminator}"],
        )


@tasks.task(ignore_result=True, acks_late=True)
def delete_expired_oidc_macaroons(request):
    """
    Purge all API tokens minted using OIDC Trusted Publishing with a creation time
    more than 1 day ago. Since OIDC-minted macaroons expire 15 minutes after
    creation, this task cleans up tokens that expired several hours ago and that
    have accumulated since the last time this task was run.
    """
    rows_deleted = (
        request.db.query(Macaroon)
        .filter(Macaroon.oidc_publisher_id.isnot(None))
        .filter(
            # The token has been created at more than 1 day ago
            Macaroon.created + timedelta(days=1) < datetime.now(tz=UTC)
        )
        .delete(synchronize_session=False)
    )
    metrics = request.find_service(IMetricsService, context=None)
    metrics.gauge(
        "warehouse.oidc.expired_oidc_tokens_deleted",
        rows_deleted,
    )


@tasks.task(ignore_result=True, acks_late=True)
def delete_expired_pending_publishers(request: Request) -> None:
    """
    Delete pending OIDC publishers that have exceeded their TTL.
    Sends a notification email to each publisher's owner before deletion.
    """
    cutoff = pending_publisher_cutoff(PENDING_PUBLISHER_EXPIRY_DAYS)
    expired_publishers = request.db.scalars(
        select(PendingOIDCPublisher).where(PendingOIDCPublisher.created < cutoff)
    ).all()

    for publisher in expired_publishers:
        send_pending_trusted_publisher_expired_email(
            request,
            publisher.added_by,
            project_name=publisher.project_name,
            days=PENDING_PUBLISHER_EXPIRY_DAYS,
        )
        publisher.added_by.record_event(
            tag=EventTag.Account.PendingOIDCPublisherRemoved,
            request=request,
            additional={
                "project": publisher.project_name,
                "publisher": publisher.publisher_name,
                "id": str(publisher.id),
                "specifier": str(publisher),
                "url": publisher.publisher_url(),
                "submitted_by": "system:ttl-expired",
                "redact_ip": True,
            },
        )
        request.db.delete(publisher)

    request.metrics.gauge(
        "warehouse.oidc.expired_pending_publishers_deleted",
        len(expired_publishers),
    )


@tasks.task(ignore_result=True, acks_late=True)
def send_pending_publisher_expiration_reminders(request: Request) -> None:
    """
    Send a one-shot reminder email for pending OIDC publishers approaching
    their TTL. The `expiration_reminded` flag prevents re-reminding.
    """
    cutoff = pending_publisher_cutoff(
        PENDING_PUBLISHER_EXPIRY_DAYS - PENDING_PUBLISHER_REMINDER_DAYS
    )
    publishers = request.db.scalars(
        select(PendingOIDCPublisher).where(
            PendingOIDCPublisher.created < cutoff,
            PendingOIDCPublisher.expiration_reminded.is_(False),
        )
    ).all()

    for publisher in publishers:
        send_pending_trusted_publisher_expiration_reminder_email(
            request,
            publisher.added_by,
            project_name=publisher.project_name,
            days_remaining=PENDING_PUBLISHER_REMINDER_DAYS,
        )
        publisher.expiration_reminded = True

    request.metrics.gauge(
        "warehouse.oidc.pending_publisher_expiration_reminders_sent",
        len(publishers),
    )
