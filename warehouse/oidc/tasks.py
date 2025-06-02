# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta, timezone

from warehouse import tasks
from warehouse.macaroons.models import Macaroon
from warehouse.metrics import IMetricsService
from warehouse.oidc.models import OIDCPublisher
from warehouse.packaging.models import File, Project, Release


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
            Macaroon.created + timedelta(days=1)
            < datetime.now(tz=timezone.utc)
        )
        .delete(synchronize_session=False)
    )
    metrics = request.find_service(IMetricsService, context=None)
    metrics.gauge(
        "warehouse.oidc.expired_oidc_tokens_deleted",
        rows_deleted,
    )
