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

from packaging.version import parse
from pyramid_jinja2 import IJinja2Environment
from sqlalchemy.orm import joinedload

from warehouse.packaging.interfaces import ISimpleStorage
from warehouse.packaging.models import File, Project, Release

API_VERSION = "1.0"


def _simple_index(request, serial):
    # Fetch the name and normalized name for all of our projects
    projects = (
        request.db.query(Project.name, Project.normalized_name)
        .order_by(Project.normalized_name)
        .all()
    )

    return {
        "meta": {"api-version": API_VERSION, "_last-serial": serial},
        "projects": [{"name": p.name} for p in projects],
    }


def _simple_detail(project, request):
    # Get all of the files for this project.
    files = sorted(
        request.db.query(File)
        .options(joinedload(File.release))
        .join(Release)
        .filter(Release.project == project)
        .all(),
        key=lambda f: (parse(f.release.version), f.filename),
    )

    return {
        "meta": {"api-version": API_VERSION, "_last-serial": project.last_serial},
        "name": project.normalized_name,
        "files": [
            {
                "filename": file.filename,
                "url": request.route_url("packaging.file", path=file.path),
                "hashes": {
                    "sha256": file.sha256_digest,
                },
                "requires-python": file.release.requires_python,
                "yanked": file.release.yanked_reason
                if file.release.yanked and file.release.yanked_reason
                else file.release.yanked,
            }
            for file in files
        ],
    }


def render_simple_detail(project, request, store=False):
    context = _simple_detail(project, request)

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
