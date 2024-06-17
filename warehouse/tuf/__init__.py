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

import requests


class RSTUFError(Exception):
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
