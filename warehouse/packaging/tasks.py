# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import contextlib
import datetime
import shutil
import tempfile
import typing

from typing import NamedTuple

import structlog

from celery.exceptions import SoftTimeLimitExceeded, TimeLimitExceeded
from packaging.utils import canonicalize_name
from requests.exceptions import RequestException
from sqlalchemy import desc, func, nulls_last, select
from sqlalchemy.orm import joinedload

from warehouse import tasks
from warehouse.accounts.interfaces import IUserService
from warehouse.accounts.models import User, WebAuthn
from warehouse.cache.interfaces import IQueryResultsCache
from warehouse.helpdesk.interfaces import IAdminNotificationService
from warehouse.metrics import IMetricsService
from warehouse.observations.models import ObservationKind
from warehouse.packaging.interfaces import IFileStorage
from warehouse.packaging.models import (
    Dependency,
    DependencyKind,
    Description,
    File,
    Project,
    Release,
)
from warehouse.packaging.typosnyper import typo_check_name
from warehouse.utils import readme
from warehouse.utils.row_counter import RowCount

if typing.TYPE_CHECKING:
    from uuid import UUID

    from pyramid.request import Request

logger = structlog.get_logger(__name__)


def _copy_file_to_cache(archive_storage, cache_storage, path):
    metadata = archive_storage.get_metadata(path)
    with (
        contextlib.closing(archive_storage.get(path)) as file_obj,
        tempfile.NamedTemporaryFile() as file_for_cache,
    ):
        shutil.copyfileobj(file_obj, file_for_cache, length=1024 * 1024)
        file_for_cache.flush()
        cache_storage.store(path, file_for_cache.name, meta=metadata)


@tasks.task(
    ignore_result=True,
    acks_late=True,
    time_limit=120,
    autoretry_for=(
        SoftTimeLimitExceeded,
        TimeLimitExceeded,
    ),
)
def sync_file_to_cache(request, file_id):
    file = request.db.get(File, file_id)

    if file and not file.cached:
        archive_storage = request.find_service(IFileStorage, name="archive")
        cache_storage = request.find_service(IFileStorage, name="cache")

        _copy_file_to_cache(archive_storage, cache_storage, file.path)
        if file.metadata_file_sha256_digest is not None:
            _copy_file_to_cache(archive_storage, cache_storage, file.metadata_path)

        file.cached = True


@tasks.task(ignore_result=True, acks_late=True)
def compute_packaging_metrics(request):
    counts = dict(
        request.db.query(RowCount.table_name, RowCount.count)
        .filter(
            RowCount.table_name.in_(
                [
                    Project.__tablename__,
                    Release.__tablename__,
                    File.__tablename__,
                ]
            )
        )
        .all()
    )

    metrics = request.find_service(IMetricsService, context=None)

    metrics.gauge(
        "warehouse.packaging.total_projects", counts.get(Project.__tablename__, 0)
    )

    metrics.gauge(
        "warehouse.packaging.total_releases", counts.get(Release.__tablename__, 0)
    )

    metrics.gauge("warehouse.packaging.total_files", counts.get(File.__tablename__, 0))


@tasks.task(ignore_result=True, acks_late=True)
def check_file_cache_tasks_outstanding(request):
    metrics = request.find_service(IMetricsService, context=None)

    files_not_cached = request.db.query(File).filter_by(cached=False).count()

    metrics.gauge(
        "warehouse.packaging.files.not_cached",
        files_not_cached,
    )


class Sizes(NamedTuple):
    file: int | None
    metadata_file: int | None


def fetch_sizes(storage, file) -> Sizes:
    try:
        file_size = storage.get_size(file.path)
    except FileNotFoundError:
        file_size = None

    try:
        metadata_file_size = storage.get_size(file.metadata_path)
    except FileNotFoundError:
        metadata_file_size = None

    return Sizes(file_size, metadata_file_size)


@tasks.task(ignore_results=True, acks_late=True)
def reconcile_file_storages(request):
    metrics = request.find_service(IMetricsService, context=None)
    cache_storage = request.find_service(IFileStorage, name="cache")
    archive_storage = request.find_service(IFileStorage, name="archive")

    batch_size = request.registry.settings["reconcile_file_storages.batch_size"]

    logger.info("Running reconcile_file_storages", batch_size=batch_size)

    # SKIP LOCKED so two concurrent runs grab separate rows instead of both
    # picking the same files and conflicting.
    files_batch = (
        request.db.query(File)
        .filter_by(cached=False)
        .with_for_update(skip_locked=True, of=File)
        .limit(batch_size)
    )

    for file in files_batch.all():
        logger.info("Checking file", file_id=file.id, path=file.path)
        archive_sizes = fetch_sizes(archive_storage, file)
        cache_sizes = fetch_sizes(cache_storage, file)

        # The archive is the golden copy, but only where it agrees with the
        # size we recorded when the file was uploaded. Sizes are used rather
        # than checksums because S3 reports a multipart ETag for anything over
        # boto3's 8MB threshold, which never equals the file's md5 digest.
        # See: https://github.com/pypi/warehouse/issues/19704
        errors = []

        if archive_sizes.file != file.size:
            metrics.increment("warehouse.filestorage.unreconciled", tags=["type:dist"])
            logger.error(
                "Unable to reconcile stored file distribution ❌",
                file_id=file.id,
                path=file.path,
                expected_size=file.size,
                archive_size=archive_sizes.file,
            )
            errors.append(file.path)
        elif cache_sizes.file != archive_sizes.file:
            _copy_file_to_cache(archive_storage, cache_storage, file.path)
            logger.info(
                "File distribution pulled from archive ⬆️",
                file_id=file.id,
                path=file.path,
            )
            metrics.increment("warehouse.filestorage.reconciled", tags=["type:dist"])
        else:
            logger.info("File distribution is ok ✅", file_id=file.id, path=file.path)

        # We don't store the METADATA file's size, so the archive is the only
        # authority on what the cache should hold.
        if file.metadata_file_sha256_digest is not None:
            if archive_sizes.metadata_file is None:
                metrics.increment(
                    "warehouse.filestorage.unreconciled", tags=["type:metadata"]
                )
                logger.error(
                    "Unable to reconcile stored file METADATA ❌",
                    file_id=file.id,
                    path=file.metadata_path,
                )
                errors.append(file.metadata_path)
            elif cache_sizes.metadata_file != archive_sizes.metadata_file:
                _copy_file_to_cache(archive_storage, cache_storage, file.metadata_path)
                logger.info(
                    "File METADATA pulled from archive ⬆️",
                    file_id=file.id,
                    path=file.metadata_path,
                )
                metrics.increment(
                    "warehouse.filestorage.reconciled", tags=["type:metadata"]
                )
            else:
                logger.info(
                    "File METADATA is ok ✅", file_id=file.id, path=file.metadata_path
                )

        if len(errors) == 0:
            file.cached = True


@tasks.task(ignore_result=True, acks_late=True)
def compute_2fa_metrics(request):
    metrics = request.find_service(IMetricsService, context=None)

    # Total number of users with TOTP enabled
    total_users_with_totp_enabled = (
        request.db.query(User).where(User.totp_secret.is_not(None)).count()
    )
    metrics.gauge(
        "warehouse.2fa.total_users_with_totp_enabled",
        total_users_with_totp_enabled,
    )

    # Total number of users with WebAuthn enabled
    metrics.gauge(
        "warehouse.2fa.total_users_with_webauthn_enabled",
        request.db.query(User.id)
        .distinct()
        .join(WebAuthn, WebAuthn.user_id == User.id)
        .count(),
    )

    # Total number of users with 2FA enabled
    metrics.gauge(
        "warehouse.2fa.total_users_with_two_factor_enabled",
        total_users_with_totp_enabled
        + request.db.query(User.id)
        .distinct()
        .join(WebAuthn, WebAuthn.user_id == User.id)
        .where(User.totp_secret.is_(None))
        .count(),
    )


@tasks.task(ignore_result=True, acks_late=True)
def update_description_html(request):
    renderer_version = readme.renderer_version()

    descriptions = (
        request.db.query(Description)
        .filter(Description.rendered_by != renderer_version)
        .yield_per(100)
        .limit(500)
    )

    for description in descriptions:
        description.html = readme.render(description.raw, description.content_type)
        description.rendered_by = renderer_version


@tasks.task(bind=True, ignore_result=True, acks_late=True)
def update_release_description(_task, request, release_id):
    """Given a release_id, update the release description via readme-renderer."""
    renderer_version = readme.renderer_version()

    release = (
        request.db.query(Release)
        .filter(Release.id == release_id)
        .options(joinedload(Release.description))
        .first()
    )

    release.description.html = readme.render(
        release.description.raw, release.description.content_type
    )
    release.description.rendered_by = renderer_version


@tasks.task(
    bind=True,
    ignore_result=True,
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=15,
    retry_jitter=False,
    max_retries=5,
)
def update_bigquery_release_files(task, request, dist_metadata) -> None:
    """
    Adds release file metadata to public BigQuery database
    """
    release_files_table = request.registry.settings.get("warehouse.release_files_table")
    if release_files_table is None:
        return

    bq = request.find_service(name="gcloud.bigquery")

    # Multiple table names can be specified by separating them with whitespace
    table_names = release_files_table.split()

    for table_name in table_names:
        table_schema = bq.get_table(table_name, timeout=5.0, retry=None).schema

        # Using the schema to populate the data allows us to automatically
        # set the values to their respective fields rather than assigning
        # values individually
        json_row: dict = {}
        for sch in table_schema:
            field_data = dist_metadata.get(sch.name, None)

            if isinstance(field_data, datetime.datetime):
                field_data = field_data.isoformat()

            # Replace all empty objects to None will ensure
            # proper checks if a field is nullable or not
            if not isinstance(field_data, bool) and not field_data:
                field_data = None

            if field_data is None and sch.mode == "REPEATED":
                json_row[sch.name] = []
            elif field_data and sch.mode == "REPEATED":
                # Currently, some of the metadata fields such as
                # the 'platform' tag are incorrectly classified as a
                # str instead of a list, hence, this workaround to comply
                # with PEP 345 and the Core Metadata specifications.
                # This extra check can be removed once
                # https://github.com/pypi/warehouse/issues/8257 is fixed
                if isinstance(field_data, str):
                    json_row[sch.name] = [field_data]
                else:
                    json_row[sch.name] = list(field_data)
            else:
                json_row[sch.name] = field_data
        json_rows = [json_row]

        bq.insert_rows_json(
            table=table_name, json_rows=json_rows, timeout=5.0, retry=None
        )


@tasks.task(ignore_result=True, acks_late=True)
def compute_top_dependents_corpus(request: Request) -> dict[str, int]:
    """
    Query to collect all dependents from projects' most recent release
    and rank them by the number of dependents.
    Store in query results cache for retrieval during `file_upload`.
    """
    # Create a CTE with the most recent releases for each project.
    # Selects each release's ID, project ID, and version, with a row number
    # partitioned by project and ordered to get the most recent non-yanked releases.
    recent_releases_cte = (
        select(
            Release.id.label("release_id"),
            Release.project_id,
            Release.version,
            func.row_number()
            .over(
                partition_by=Release.project_id,
                order_by=[
                    nulls_last(
                        Release.is_prerelease
                    ),  # False first, True next, nulls last
                    desc(Release._pypi_ordering),
                ],
            )
            .label("rn"),
        )
        .where(Release.yanked.is_(False))
        .cte("recent_releases")
    )
    # Create a CTE that parses dependency names from release_dependencies.
    #
    # Extracts normalized dependency names by:
    # 1. Taking the specifier from release_dependencies
    # 2. Using regex to extract just the package name portion
    # 3. Converting to lowercase for normalization
    parsed_dependencies_cte = (
        select(
            func.normalize_pep426_name(
                # TODO: this isn't perfect, but it's a start.
                #  A better solution would be to use a proper parser, but we'd need
                #  to teach Postgres how to parse it.
                func.regexp_replace(Dependency.specifier, "^([A-Za-z0-9_.-]+).*", "\\1")
            ).label("dependent_name")
        )
        .select_from(recent_releases_cte)
        .join(Dependency, Dependency.release_id == recent_releases_cte.c.release_id)
        .where(
            recent_releases_cte.c.rn == 1,  # "latest" release per-project
            Dependency.kind.in_(
                [DependencyKind.requires_dist, DependencyKind.requires]
            ),
        )
        .cte("parsed_dependencies")
    )

    # Final query that gets the top dependents by count
    top_dependents_stmt = (
        select(
            parsed_dependencies_cte.c.dependent_name,
            func.count().label("dependent_count"),
        )
        .group_by(parsed_dependencies_cte.c.dependent_name)
        .order_by(desc("dependent_count"), parsed_dependencies_cte.c.dependent_name)
        .limit(10000)
    )

    # Execute the query and fetch the constructed object
    results = request.db.execute(top_dependents_stmt).fetchall()
    # Result is Rows, so convert to a dicts of "name: count" pairs
    results = {row.dependent_name: row.dependent_count for row in results}

    # Store the results in the query results cache
    cache = request.find_service(IQueryResultsCache)
    cache_key = "top_dependents_corpus"
    cache.set(cache_key, results)
    logger.info("Stored `top_dependents_corpus` in query results cache.")

    return results


@tasks.task(
    ignore_result=True,
    acks_late=True,
    autoretry_for=(RequestException,),
    retry_backoff=True,
)
def typo_check_project_name(request: Request, project_id: UUID) -> None:
    """
    Check a newly created project name for typo-squatting of a popular project,
    recording an observation and notifying admins for review when it looks like
    a typo.

    Enqueued by project creation and dispatched only once that transaction
    commits, so we neither run the checks nor notify for a project that was
    never created.
    """
    project = request.db.get(Project, project_id)
    if project is None:
        # The project was removed between creation and this task running.
        logger.info("Project no longer exists, skipping typo check.")
        return

    project_name = project.name
    corpus = request.find_service(IQueryResultsCache).get("top_dependents_corpus")
    typo_check_match = typo_check_name(canonicalize_name(project_name), corpus=corpus)
    if typo_check_match is None:
        return

    check_name, existing_project_name = typo_check_match

    logger.warning(
        "Project name detected as a potential typo",
        project_name=project_name,
        check_name=check_name,
        existing_project_name=existing_project_name,
    )

    # Annotate the project for admin review. This is a record only - the kind is
    # not one that any of the observation reactions act on, so nothing about the
    # project's lifecycle changes.
    project.record_observation(
        request=request,
        kind=ObservationKind.IsTypoSnyperMatch,
        actor=request.find_service(IUserService).get_admin_user(),
        summary=f"Potential typo of {existing_project_name!r}",
        payload={
            "check_name": check_name,
            "existing_project_name": existing_project_name,
            "origin": "typosnyper",
        },
    )

    warehouse_domain = request.registry.settings.get("warehouse.domain")
    new_project_page = request.route_url(
        "packaging.project",
        name=project_name,
        _host=warehouse_domain,
    )
    new_project_text = (
        f"Project Create for *<{new_project_page}|{project_name}>* was "
        f"detected as a potential typo by the `{check_name!r}` check."
    )
    existing_project_page = request.route_url(
        "packaging.project",
        name=existing_project_name,
        _host=warehouse_domain,
    )
    existing_project_text = (
        f"<{existing_project_page}|Existing project: {existing_project_name}>"
    )

    webhook_payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "TypoSnyper :warning:",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": new_project_text},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": existing_project_text},
            },
            {"type": "divider"},
            {
                "type": "context",
                "elements": [
                    {
                        "type": "plain_text",
                        "text": "Once reviewed/confirmed, "
                        "react to this message with :white_check_mark:",
                        "emoji": True,
                    }
                ],
            },
        ]
    }
    notification_service = request.find_service(IAdminNotificationService)
    notification_service.send_notification(payload=webhook_payload)

    metrics = request.find_service(IMetricsService, context=None)
    metrics.increment(
        "warehouse.packaging.services.create_project.typo_squatting",
        tags=[f"check_name:{check_name!r}"],
    )
