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

"""
RSTUF API client library
"""

import time

from typing import Any
from uuid import UUID

import requests

from pyramid.request import Request

from warehouse import tasks
from warehouse.packaging.models import Project
from warehouse.packaging.utils import render_simple_detail


class RSTUFError(Exception):
    pass


class RSTUFNoBootstrapError(Exception):
    pass


def get_task_state(server: str, task_id: str) -> str:
    resp = requests.get(f"{server}/api/v1/task?task_id={task_id}")
    resp.raise_for_status()
    return resp.json()["data"]["state"]


def post_bootstrap(server: str, payload: Any) -> str:
    resp = requests.post(f"{server}/api/v1/bootstrap", json=payload)
    resp.raise_for_status()

    # TODO: Ask upstream to not return 200 on error
    resp_json = resp.json()
    resp_data = resp_json.get("data")
    if not resp_data:
        raise RSTUFError(f"Error in RSTUF job: {resp_json}")

    return resp_data["task_id"]


def post_artifacts(server: str, payload: Any) -> str:
    """Call RSTUF artifacts API to update the relevant TUF metadata.

    Returns task id of the async update task in RSTUF.
    """
    resp = requests.post(f"{server}/api/v1/artifacts", json=payload)
    resp.raise_for_status()

    # 200 but no "data" means that RSTUF isn't bootstrapped yet
    # TODO: Ask upstream to not return 200 on error
    resp_json = resp.json()
    resp_data = resp_json.get("data")
    if not resp_data:
        raise RSTUFNoBootstrapError(resp_json)

    return resp_data["task_id"]


def wait_for_success(server: str, task_id: str):
    """Poll RSTUF task state API until success or error."""

    retries = 20
    delay = 1

    for _ in range(retries):
        state = get_task_state(server, task_id)

        match state:
            case "SUCCESS":
                break

            case "PENDING" | "RUNNING" | "RECEIVED" | "STARTED":
                time.sleep(delay)
                continue

            case "FAILURE":
                raise RSTUFError("RSTUF job failed, please check payload and retry")

            case "ERRORED" | "REVOKED" | "REJECTED":
                raise RSTUFError("RSTUF internal problem, please check RSTUF health")

            case _:
                raise RSTUFError(f"RSTUF job returned unexpected state: {state}")

    else:
        raise RSTUFError("RSTUF job failed, please check payload and retry")


@tasks.task(ignore_result=True, acks_late=True)
def update_metadata(request: Request, project_id: UUID):
    """Update TUF metadata to capture project changes (PEP 458).

    NOTE: PEP 458 says, TUF targets metadata must include path, hash and size of
    distributions files and simple detail files. In reality, simple detail files
    are enough, as they already include all relevant distribution file infos.
    """
    server = request.registry.settings["tuf.rstuf_api_url"]
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
