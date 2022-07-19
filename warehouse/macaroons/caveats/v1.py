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

import json
import time

from warehouse.macaroons.caveats.base import Caveat
from warehouse.packaging.models import Project


class V1Caveat(Caveat):
    def verify_projects(self, projects) -> bool:
        # First, ensure that we're actually operating in
        # the context of a package.
        if not isinstance(self.verifier.context, Project):
            self.failure_reason = (
                "project-scoped token used outside of a project context"
            )
            return False

        project = self.verifier.context
        if project.normalized_name in projects:
            return True

        self.failure_reason = (
            f"project-scoped token is not valid for project '{project.name}'"
        )
        return False

    def verify(self, predicate) -> bool:
        try:
            data = json.loads(predicate)
        except ValueError:
            self.failure_reason = "malformatted predicate"
            return False

        if data.get("version") != 1:
            self.failure_reason = "invalid version in predicate"
            return False

        permissions = data.get("permissions")
        if permissions is None:
            self.failure_reason = "invalid permissions in predicate"
            return False

        if permissions == "user":
            # User-scoped tokens behave exactly like a user's normal credentials.
            return True

        projects = permissions.get("projects")
        if projects is None:
            self.failure_reason = "invalid projects in predicate"
            return False

        return self.verify_projects(projects)


class ExpiryCaveat(Caveat):
    def verify(self, predicate):
        try:
            data = json.loads(predicate)
            expiry = data["exp"]
            not_before = data["nbf"]
        except (KeyError, ValueError, TypeError):
            self.failure_reason = "malformatted predicate"
            return False

        if not expiry or not not_before:
            self.failure_reason = "missing fields"
            return False

        now = int(time.time())
        if now < not_before or now >= expiry:
            self.failure_reason = "token is expired"
            return False

        return True


class ProjectIDsCaveat(Caveat):
    def verify(self, predicate):
        try:
            data = json.loads(predicate)
            project_ids = data["project_ids"]
        except (KeyError, ValueError, TypeError):
            self.failure_reason = "malformatted predicate"
            return False

        if not project_ids:
            self.failure_reason = "missing fields"
            return False

        if not isinstance(self.verifier.context, Project):
            self.failure_reason = (
                "project-scoped token used outside of a project context"
            )
            return False

        if str(self.verifier.context.id) not in project_ids:
            self.failure_reason = "current project does not matched scoped project IDs"
            return False

        return True
