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

import requests

from pyramid.httpexceptions import HTTPBadGateway

from warehouse.packaging.models import File
from warehouse.packaging.utils import current_simple_details_path, render_simple_detail


def _payload(targets):
    """Helper to create payload for POST or DELETE targets request."""
    return {
        "targets": targets,
        "publish_targets": True,
    }


def _payload_targets_part(path, size, digest):
    """Helper to create payload part for POST targets request."""
    return {
        "path": path,
        "info": {
            "length": size,
            "hashes": {"blake2b-256": digest},
        },
    }


def _handle(response):
    """Helper to handle http response for POST or DELETE targets request."""
    if response.status_code != 202:
        raise HTTPBadGateway(f"Unexpected TUF Server response: {response.text}")

    return response.json()


def add_file(request, project, file=None):
    """Call RSTUF to add file and new project simple index to TUF targets metadata.

    NOTE: If called without file, only adds new project simple index. This
    can be used to re-add project simple index, after deleting a file.
    """
    targets = []
    digest, path, size = render_simple_detail(project, request, store=True)
    simple_index_part = _payload_targets_part(path, size, digest)
    targets.append(simple_index_part)
    if file:
        file_part = _payload_targets_part(file.path, file.size, file.blake2_256_digest)
        targets.append(file_part)

    response = requests.post(
        request.registry.settings["tuf.api.targets.url"], json=_payload(targets)
    )

    return _handle(response)


def delete_file(request, project, file):
    """Call RSTUF to remove file and project simple index from TUF targets metadata.

    NOTE: Simple index needs to be added separately.
    """
    index_path = current_simple_details_path(request, project)
    targets = [file.path, index_path]

    response = requests.delete(
        request.registry.settings["tuf.api.targets.url"], json=_payload(targets)
    )

    return _handle(response)


def delete_release(request, release):
    files = request.db.query(File).filter(File.release_id == release.id).all()

    tasks = []
    for file in files:
        tasks.append(delete_file(request, release.project, file))

    return tasks
