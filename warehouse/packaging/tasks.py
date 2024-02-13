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
import hashlib
import logging
import os
import tempfile

from collections import namedtuple
from itertools import product
from pathlib import Path

from google.cloud.bigquery import LoadJobConfig
from pip._internal.network.lazy_wheel import dist_from_wheel_url
from pip._internal.network.session import PipSession
from sqlalchemy import desc
from sqlalchemy.orm import joinedload

from warehouse import tasks
from warehouse.accounts.models import User, WebAuthn
from warehouse.metrics import IMetricsService
from warehouse.packaging.interfaces import IFileStorage
from warehouse.packaging.models import Description, File, Project, Release
from warehouse.utils import readme
from warehouse.utils.row_counter import RowCount

logger = logging.getLogger(__name__)


def _copy_file_to_cache(archive_storage, cache_storage, path):
    metadata = archive_storage.get_metadata(path)
    file_obj = archive_storage.get(path)
    with tempfile.NamedTemporaryFile() as file_for_cache:
        file_for_cache.write(file_obj.read())
        file_for_cache.flush()
        cache_storage.store(path, file_for_cache.name, meta=metadata)


@tasks.task(ignore_result=True, acks_late=True)
def sync_file_to_cache(request, file_id):
    file = request.db.get(File, file_id)
    if not file.cached:
        archive_storage = request.find_service(IFileStorage, name="archive")
        cache_storage = request.find_service(IFileStorage, name="cache")

        _copy_file_to_cache(archive_storage, cache_storage, file.path)
        if file.metadata_file_sha256_digest is not None:
            _copy_file_to_cache(archive_storage, cache_storage, file.metadata_path)

        file.cached = True


@tasks.task(ignore_result=True, acks_late=True)
def backfill_metadata(request):
    metrics = request.find_service(IMetricsService, context=None)
    base_url = request.registry.settings.get("files.url")

    archive_storage = request.find_service(IFileStorage, name="archive")
    cache_storage = request.find_service(IFileStorage, name="cache")
    session = PipSession()

    # Get all wheel files without metadata in reverse chronologicial order
    files_without_metadata = (
        request.db.query(File)
        .filter(File.packagetype == "bdist_wheel")
        .filter(File.metadata_file_sha256_digest.is_(None))
        .order_by(desc(File.upload_time))
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        for file_ in files_without_metadata.yield_per(100):
            # Use pip to download just the metadata of the wheel
            file_url = base_url.format(path=file_.path)
            lazy_dist = dist_from_wheel_url(
                file_.release.project.normalized_name, file_url, session
            )
            wheel_metadata_contents = lazy_dist._dist._files[Path("METADATA")]

            # Write the metadata to a temporary file
            temporary_filename = os.path.join(tmpdir, file_.filename) + ".metadata"
            with open(temporary_filename, "wb") as fp:
                fp.write(wheel_metadata_contents)

            # Hash the metadata and add it to the File instance
            file_.metadata_file_sha256_digest = (
                hashlib.sha256(wheel_metadata_contents).hexdigest().lower()
            )
            file_.metadata_file_blake2_256_digest = (
                hashlib.blake2b(wheel_metadata_contents, digest_size=256 // 8)
                .hexdigest()
                .lower()
            )

            # Store the metadata file via our object storage backend
            archive_storage.store(
                file_.metadata_path,
                temporary_filename,
                meta={
                    "project": file_.release.project.normalized_name,
                    "version": file_.release.version,
                    "package-type": file_.packagetype,
                    "python-version": file_.python_version,
                },
            )
            # Write it to our storage cache as well
            cache_storage.store(
                file_.metadata_path,
                temporary_filename,
                meta={
                    "project": file_.release.project.normalized_name,
                    "version": file_.release.version,
                    "package-type": file_.packagetype,
                    "python-version": file_.python_version,
                },
            )
            metrics.increment("warehouse.packaging.metadata_backfill.files")
        metrics.increment("warehouse.packaging.metadata_backfill.tasks")
    metrics.gauge(
        "warehouse.packaging.metadata_backfill.remaining",
        files_without_metadata.count(),
    )


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


Checksums = namedtuple("Checksums", ["file", "metadata_file"])


def fetch_checksums(storage, file):
    try:
        file_checksum = storage.get_checksum(file.path)
    except FileNotFoundError:
        file_checksum = None

    try:
        file_metadata_checksum = storage.get_checksum(file.metadata_path)
    except FileNotFoundError:
        file_metadata_checksum = None

    return Checksums(file_checksum, file_metadata_checksum)


@tasks.task(ignore_results=True, acks_late=True)
def reconcile_file_storages(request):
    metrics = request.find_service(IMetricsService, context=None)
    cache_storage = request.find_service(IFileStorage, name="cache")
    archive_storage = request.find_service(IFileStorage, name="archive")

    batch_size = request.registry.settings["reconcile_file_storages.batch_size"]

    logger.info(f"Running reconcile_file_storages with batch_size {batch_size}...")

    files_batch = request.db.query(File).filter_by(cached=False).limit(batch_size)

    for file in files_batch.all():
        logger.info(f"Checking File<{file.id}> ({file.path})...")
        archive_checksums = fetch_checksums(archive_storage, file)
        cache_checksums = fetch_checksums(cache_storage, file)

        # Note: We don't store md5 digest for METADATA file in our database,
        # record boolean for if we should expect values.
        expected_checksums = Checksums(
            file.md5_digest,
            bool(file.metadata_file_sha256_digest),
        )

        if (
            (archive_checksums == cache_checksums)
            and (archive_checksums.file == expected_checksums.file)
            and (
                bool(archive_checksums.metadata_file)
                == expected_checksums.metadata_file
            )
        ):
            logger.info(f"    File<{file.id}> ({file.path}) is all good ✨")
            file.cached = True
        else:
            errors = []

            if (archive_checksums.file != cache_checksums.file) and (
                archive_checksums.file == expected_checksums.file
            ):
                # No worries, a consistent file is in archive but not cache
                _copy_file_to_cache(archive_storage, cache_storage, file.path)
                logger.info(
                    f"    File<{file.id}> distribution ({file.path}) "
                    "pulled from archive ⬆️"
                )
                metrics.increment(
                    "warehouse.filestorage.reconciled", tags=["type:dist"]
                )
            elif (
                archive_checksums.file == cache_checksums.file
                and archive_checksums.file is not None
            ):
                logger.info(f"    File<{file.id}> distribution ({file.path}) is ok ✅")
            else:
                metrics.increment(
                    "warehouse.filestorage.unreconciled", tags=["type:dist"]
                )
                logger.error(
                    f"Unable to reconcile stored File<{file.id}> distribution "
                    f"({file.path}) ❌"
                )
                errors.append(file.path)

            if expected_checksums.metadata_file and (
                archive_checksums.metadata_file is not None
                and cache_checksums.metadata_file is None
            ):
                # The only file we have is in archive, so use that for cache
                _copy_file_to_cache(archive_storage, cache_storage, file.metadata_path)
                logger.info(
                    f"    File<{file.id}> METADATA ({file.metadata_path}) "
                    "pulled from archive ⬆️"
                )
                metrics.increment(
                    "warehouse.filestorage.reconciled", tags=["type:metadata"]
                )
            elif expected_checksums.metadata_file:
                if archive_checksums.metadata_file == cache_checksums.metadata_file:
                    logger.info(
                        f"    File<{file.id}> METADATA ({file.metadata_path}) is ok ✅"
                    )
                else:
                    metrics.increment(
                        "warehouse.filestorage.unreconciled", tags=["type:metadata"]
                    )
                    logger.error(
                        f"Unable to reconcile stored File<{file.id}> METADATA "
                        f"({file.metadata_path}) ❌"
                    )
                    errors.append(file.metadata_path)

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
def update_bigquery_release_files(task, request, dist_metadata):
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
        table_schema = bq.get_table(table_name).schema

        # Using the schema to populate the data allows us to automatically
        # set the values to their respective fields rather than assigning
        # values individually
        json_rows = dict()
        for sch in table_schema:
            field_data = dist_metadata[sch.name]

            if isinstance(field_data, datetime.datetime):
                field_data = field_data.isoformat()

            # Replace all empty objects to None will ensure
            # proper checks if a field is nullable or not
            if not isinstance(field_data, bool) and not field_data:
                field_data = None

            if field_data is None and sch.mode == "REPEATED":
                json_rows[sch.name] = []
            elif field_data and sch.mode == "REPEATED":
                # Currently, some of the metadata fields such as
                # the 'platform' tag are incorrectly classified as a
                # str instead of a list, hence, this workaround to comply
                # with PEP 345 and the Core Metadata specifications.
                # This extra check can be removed once
                # https://github.com/pypi/warehouse/issues/8257 is fixed
                if isinstance(field_data, str):
                    json_rows[sch.name] = [field_data]
                else:
                    json_rows[sch.name] = list(field_data)
            else:
                json_rows[sch.name] = field_data
        json_rows = [json_rows]

        bq.insert_rows_json(table=table_name, json_rows=json_rows)


@tasks.task(ignore_result=True, acks_late=True)
def sync_bigquery_release_files(request):
    release_files_table = request.registry.settings.get("warehouse.release_files_table")
    if release_files_table is None:
        return

    bq = request.find_service(name="gcloud.bigquery")

    # Multiple table names can be specified by separating them with whitespace
    table_names = release_files_table.split()

    for table_name in table_names:
        table_schema = bq.get_table(table_name).schema

        # Using the schema to populate the data allows us to automatically
        # set the values to their respective fields rather than assigning
        # values individually
        def populate_data_using_schema(file):
            release = file.release
            project = release.project

            row_data = dict()
            for sch in table_schema:
                # The order of data extraction below is determined based on the
                # classes that are most recently updated
                if hasattr(file, sch.name):
                    field_data = getattr(file, sch.name)
                elif hasattr(release, sch.name) and sch.name == "description":
                    field_data = getattr(release, sch.name).raw
                elif sch.name == "description_content_type":
                    field_data = getattr(release, "description").content_type
                elif hasattr(release, sch.name):
                    field_data = getattr(release, sch.name)
                elif hasattr(project, sch.name):
                    field_data = getattr(project, sch.name)
                else:
                    field_data = None

                if isinstance(field_data, datetime.datetime):
                    field_data = field_data.isoformat()

                # Replace all empty objects to None will ensure
                # proper checks if a field is nullable or not
                if not isinstance(field_data, bool) and not field_data:
                    field_data = None

                if field_data is None and sch.mode == "REPEATED":
                    row_data[sch.name] = []
                elif field_data and sch.mode == "REPEATED":
                    # Currently, some of the metadata fields such as
                    # the 'platform' tag are incorrectly classified as a
                    # str instead of a list, hence, this workaround to comply
                    # with PEP 345 and the Core Metadata specifications.
                    # This extra check can be removed once
                    # https://github.com/pypi/warehouse/issues/8257 is fixed
                    if isinstance(field_data, str):
                        row_data[sch.name] = [field_data]
                    else:
                        row_data[sch.name] = list(field_data)
                else:
                    row_data[sch.name] = field_data
            row_data["has_signature"] = False
            return row_data

        for first, second in product("fedcba9876543210", repeat=2):
            db_release_files = (
                request.db.query(File.md5_digest)
                .filter(File.md5_digest.like(f"{first}{second}%"))
                .yield_per(1000)
                .all()
            )
            db_file_digests = [file.md5_digest for file in db_release_files]

            bq_file_digests = bq.query(
                "SELECT md5_digest "
                f"FROM {table_name} "
                f"WHERE md5_digest LIKE '{first}{second}%'"
            ).result()
            bq_file_digests = [row.get("md5_digest") for row in bq_file_digests]

            md5_diff_list = list(set(db_file_digests) - set(bq_file_digests))[:1000]
            if not md5_diff_list:
                # There are no files that need synced to BigQuery
                continue

            release_files = (
                request.db.query(File)
                .join(Release, Release.id == File.release_id)
                .filter(File.md5_digest.in_(md5_diff_list))
                .all()
            )

            json_rows = [populate_data_using_schema(file) for file in release_files]

            bq.load_table_from_json(
                json_rows, table_name, job_config=LoadJobConfig(schema=table_schema)
            ).result()
            break
