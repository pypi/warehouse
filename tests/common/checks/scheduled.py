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

from warehouse.malware.checks.base import MalwareCheckBase
from warehouse.malware.models import VerdictClassification, VerdictConfidence
from warehouse.packaging.models import Project


class ExampleScheduledCheck(MalwareCheckBase):

    version = 1
    short_description = "An example scheduled check"
    long_description = "The purpose of this check is to test the \
implementation of a scheduled check. This check will generate verdicts if enabled."
    check_type = "scheduled"
    schedule = {"minute": "0", "hour": "*/8"}

    def __init__(self, db):
        super().__init__(db)

    def scan(self, **kwargs):
        project = self.db.query(Project).first()
        self.add_verdict(
            project_id=project.id,
            classification=VerdictClassification.Benign,
            confidence=VerdictConfidence.High,
            message="Nothing to see here!",
        )
