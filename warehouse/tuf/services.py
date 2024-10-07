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
import time

from requests import Session
from zope.interface import implementer

from warehouse.tuf.interfaces import ITUFService


class RSTUFError(Exception):
    pass


class RSTUFNoBootstrapError(Exception):
    pass


@implementer(ITUFService)
class RSTUFService:
    def __init__(self, api_url, retries=20, delay=1):
        self.requests = Session()
        self.api_url = api_url
        # TODO make retries and delay configurable
        self.retries = retries
        self.delay = delay

    @classmethod
    def create_service(cls, db_session):
        return cls(db_session.registry.settings["rstuf.api_url"])

    def get_task_state(self, task_id):
        """Get the RSTUF task state based on the task id."""
        response = self.requests.get(f"{self.api_url}/api/v1/task?task_id={task_id}")
        response.raise_for_status()
        return response.json()["data"]["state"]

    def post_artifacts(self, payload):
        """Call RSTUF artifacts API to update the relevant TUF metadata.

        Returns task id of the async update task in RSTUF.
        """
        response = self.requests.post(f"{self.api_url}/api/v1/artifacts", json=payload)
        response.raise_for_status()

        response_json = response.json()
        response_data = response_json.get("data")

        return response_data["task_id"]

    def wait_for_success(self, task_id):
        """Poll RSTUF task state API until success or error."""
        for _ in range(self.retries):
            state = self.get_task_state(task_id)

            match state:
                case "SUCCESS":
                    break

                case "PENDING" | "RUNNING" | "RECEIVED" | "STARTED":
                    time.sleep(self.delay)
                    continue

                case "FAILURE":
                    raise RSTUFError("RSTUF job failed, please check payload and retry")

                case "ERRORED" | "REVOKED" | "REJECTED":
                    raise RSTUFError(
                        "RSTUF internal problem, please check RSTUF health"
                    )

                case _:
                    raise RSTUFError(f"RSTUF job returned unexpected state: {state}")

        else:
            raise RSTUFError("RSTUF job failed, please check payload and retry")


def rstuf_factory(context, db_session):
    return RSTUFService(db_session.registry.settings["rstuf.api_url"])
