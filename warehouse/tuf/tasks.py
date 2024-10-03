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
from uuid import UUID

from pyramid.request import Request

from warehouse import tasks
from warehouse.packaging.models import Project
from warehouse.packaging.utils import render_simple_detail
from warehouse.tuf import post_artifacts, wait_for_success


@tasks.task(ignore_result=True, acks_late=True)
def update_metadata(request: Request, project_id: UUID):
    """Update TUF metadata to capture project changes (PEP 458).

    NOTE: PEP 458 says, TUF targets metadata must include path, hash and size of
    distributions files and simple detail files. In reality, simple detail files
    are enough, as they already include all relevant distribution file infos.
    """
    server = request.registry.settings["rstuf.api_url"]
    if not server:
        return

    project = request.db.query(Project).filter(Project.id == project_id).one()

    # NOTE: We ignore the returned simple detail path with the content hash as
    # infix. In TUF metadata the project name and hash are listed separately, so
    # that there is only one entry per target file, even if the content changes.
    digest, _, size = render_simple_detail(project, request, store=True)
    payload = {
        "targets": [
            {
                "path": project.normalized_name,
                "info": {
                    "length": size,
                    "hashes": {"blake2b-256": digest},
                },
            }
        ]
    }

    # TODO: Handle errors: pass, retry or notify
    task_id = post_artifacts(server, payload)
    wait_for_success(server, task_id)
