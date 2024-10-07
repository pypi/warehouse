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

from zope.interface import Interface


class ITUFService(Interface):
    def create_service(db_session):
        """
        Create appropriate RSTUF service based on environment
        """

    def get_task_state(task_id):
        """
        Fetch the RSTUF task state to based on the task id
        """

    def post_artifacts(payload):
        """
        Send the Artifacts payload to RSTUF API
        """

    def wait_for_success(task_id):
        """
        Wait for the RSTUF task to complete successfully
        """
