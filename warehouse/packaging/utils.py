# SPDX-License-Identifier: Apache-2.0

import hashlib
import os.path
import tempfile

import packaging_legacy.version

from pyramid_jinja2 import IJinja2Environment
from sqlalchemy import String, cast, func, select

from warehouse.packaging.interfaces import ISimpleStorage
from warehouse.packaging.models import File, LifecycleStatus, Project, Release

API_VERSION = "1.4"


def _simple_index(request, serial):
    # Fetch the name and last serial name for all of our projects
    query = select(
        func.array(
            select(
                func.json_build_object(
                    cast("name", String),
                    Project.name,
                    cast("_last-serial", String),
                    Project.last_serial,
                )
            )
            # Exclude projects that are in the `quarantine-enter` lifecycle status.
            # Use `is_distinct_from` method here to ensure that we select `NULL`
            # records, which would otherwise be excluded by the `==` operator.
            .filter(
                Project.lifecycle_status.is_distinct_from(
                    LifecycleStatus.QuarantineEnter
                )
            )
            .order_by(Project.normalized_name)
            .scalar_subquery()
        )
    )
    projects = request.db.execute(query).scalar() or []

    return {
        "meta": {"api-version": API_VERSION, "_last-serial": serial},
        "projects": projects,
    }


def _simple_detail(project, request):
    query = (
        select(
            Release.version.label("release__version"),
            Release.requires_python.label("release__requires_python"),
            Release.yanked.label("release__yanked"),
            Release.yanked_reason.label("release__yanked_reason"),
            File.filename,
            File.path,
            File.sha256_digest,
            File.size,
            File.upload_time,
            File.metadata_file_sha256_digest,
            File.provenance.has().label("has_provenance"),
        )
        .select_from(File)
        .join(File.release)
        .where(
            Release.project == project,
            # Exclude releases that are in the `quarantine-enter` lifecycle status.
            # Use `is_distinct_from` to keep NULL (unset) statuses.
            Release.lifecycle_status.is_distinct_from(LifecycleStatus.QuarantineEnter),
        )
    )

    # short-circuit here before querying the database for a result we will throw away
    if project.lifecycle_status == LifecycleStatus.QuarantineEnter:
        files = []
        versions = []
    else:
        files = sorted(
            request.db.execute(query),
            key=lambda f: (
                packaging_legacy.version.parse(f.release__version),
                f.filename,
            ),
        )
        versions = sorted(
            {f.release__version for f in files}, key=packaging_legacy.version.parse
        )

    return {
        "meta": {"api-version": API_VERSION, "_last-serial": project.last_serial},
        "name": project.normalized_name,
        "project-status": (
            {
                "status": project.project_status.value,
            }
        ),
        "versions": versions,
        "files": [
            {
                "filename": file.filename,
                "url": request.route_url("packaging.file", path=file.path),
                "hashes": {
                    "sha256": file.sha256_digest,
                },
                "requires-python": (file.release__requires_python or None),
                "size": file.size,
                "upload-time": file.upload_time.isoformat() + "Z",
                "yanked": (
                    file.release__yanked_reason
                    if file.release__yanked and file.release__yanked_reason
                    else file.release__yanked
                ),
                "data-dist-info-metadata": (
                    {"sha256": file.metadata_file_sha256_digest}
                    if file.metadata_file_sha256_digest
                    else False
                ),
                "core-metadata": (
                    {"sha256": file.metadata_file_sha256_digest}
                    if file.metadata_file_sha256_digest
                    else False
                ),
                "provenance": (
                    request.route_url(
                        "integrity.provenance",
                        project_name=project.normalized_name,
                        release=file.release__version,
                        filename=file.filename,
                    )
                    if file.has_provenance
                    else None
                ),
            }
            for file in files
        ],
    }


def render_simple_detail(project, request, store=False):
    context = _simple_detail(project, request)
    context = _valid_simple_detail_context(context)

    env = request.registry.queryUtility(IJinja2Environment, name=".jinja2")
    template = env.get_template("templates/api/simple/detail.html")
    content = template.render(**context, request=request)

    content_hasher = hashlib.blake2b(digest_size=256 // 8)
    content_hasher.update(content.encode("utf-8"))
    content_hash = content_hasher.hexdigest().lower()

    simple_detail_path = (
        f"{project.normalized_name}/{content_hash}.{project.normalized_name}.html"
    )

    if store:
        storage = request.find_service(ISimpleStorage)
        with tempfile.NamedTemporaryFile() as f:
            f.write(content.encode("utf-8"))
            f.flush()

            storage.store(
                simple_detail_path,
                f.name,
                meta={
                    "project": project.normalized_name,
                    "pypi-last-serial": project.last_serial,
                    "hash": content_hash,
                },
            )
            storage.store(
                os.path.join(project.normalized_name, "index.html"),
                f.name,
                meta={
                    "project": project.normalized_name,
                    "pypi-last-serial": project.last_serial,
                    "hash": content_hash,
                },
            )

    return (content_hash, simple_detail_path)


def _valid_simple_detail_context(context: dict) -> dict:
    context["project_status"] = context.pop("project-status", None)
    return context
