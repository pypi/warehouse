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

import hashlib
import os.path
import tempfile

import packaging_legacy.version

from pyramid_jinja2 import IJinja2Environment
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from warehouse.organizations.models import Namespace
from warehouse.packaging.interfaces import ISimpleStorage
from warehouse.packaging.models import File, LifecycleStatus, Project, Release

API_VERSION = "1.3"


def _simple_index(request, serial):
    # Fetch the name and normalized name for all of our projects
    projects = (
        request.db.query(Project.name, Project.normalized_name, Project.last_serial)
        # Exclude projects that are in the `quarantine-enter` lifecycle status.
        # Use `is_distinct_from` method here to ensure that we select `NULL` records,
        # which would otherwise be excluded by the `==` operator.
        .filter(
            Project.lifecycle_status.is_distinct_from(LifecycleStatus.QuarantineEnter)
        )
        .order_by(Project.normalized_name)
        .all()
    )

    return {
        "meta": {"api-version": API_VERSION, "_last-serial": serial},
        "projects": [{"name": p.name, "_last-serial": p.last_serial} for p in projects],
    }


def _simple_detail(project, request):
    # Get the namespace information for this project.
    # TODO: The PEP states that if we get multiple matching namespaces, it must
    #       be the one with the most characters, but does that mean that if orgA
    #       owns the NS `foo`, and delegates `foo-bar` to orgB, that orgA's grant
    #       on `foo` does not authorize them to release a package under `foo-bar`?
    namespace = None
    if (
        ns := request.db.query(Namespace)
        .filter(
            (
                (Namespace.normalized_name == project.normalized_name)
                | func.starts_with(
                    project.normalized_name,
                    func.concat(Namespace.normalized_name, "-"),
                )
            )
            & (Namespace.is_approved == True)  # noqa E712
        )
        .order_by(func.length(Namespace.normalized_name).desc())
        .first()
    ):
        namespace = {
            "prefix": ns.normalized_name,
            "authorized": ns.is_project_authorized(project),
            "open": ns.is_open,
        }

    # Get all of the files for this project.
    files = sorted(
        request.db.query(File)
        .options(joinedload(File.release))
        .join(Release)
        .filter(Release.project == project)
        # Exclude projects that are in the `quarantine-enter` lifecycle status.
        .join(Project)
        .filter(
            Project.lifecycle_status.is_distinct_from(LifecycleStatus.QuarantineEnter)
        )
        .all(),
        key=lambda f: (packaging_legacy.version.parse(f.release.version), f.filename),
    )
    versions = sorted(
        {f.release.version for f in files}, key=packaging_legacy.version.parse
    )
    alternate_repositories = sorted(
        alt_repo.url for alt_repo in project.alternate_repositories
    )

    return {
        "meta": {"api-version": API_VERSION, "_last-serial": project.last_serial},
        "name": project.normalized_name,
        "namespace": namespace,
        "versions": versions,
        "alternate-locations": alternate_repositories,
        "files": [
            {
                "filename": file.filename,
                "url": request.route_url("packaging.file", path=file.path),
                "hashes": {
                    "sha256": file.sha256_digest,
                },
                "requires-python": (
                    file.release.requires_python
                    if file.release.requires_python
                    else None
                ),
                "size": file.size,
                "upload-time": file.upload_time.isoformat() + "Z",
                "yanked": (
                    file.release.yanked_reason
                    if file.release.yanked and file.release.yanked_reason
                    else file.release.yanked
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
                        release=file.release.version,
                        filename=file.filename,
                    )
                    if file.provenance
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
    context["alternate_locations"] = context.pop("alternate-locations", [])
    return context
