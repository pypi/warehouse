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

import pymacaroons

from warehouse.packaging.models import Project


class Caveat:
    def __init__(self, verifier):
        self.verifier = verifier

    def verify(self, predicate):
        return False

    def __call__(self, predicate):
        return self.verify(predicate)


class V1Caveat(Caveat):
    def verify_projects(self, projects):
        # First, ensure that we're actually operating in
        # the context of a package.
        if not isinstance(self.verifier.context, Project):
            return False

        project = self.verifier.context
        if project.name in projects:
            return True

        return False

    def verify(self, predicate):
        try:
            data = json.loads(predicate)
        except ValueError:
            return False

        if data.get("version") != 1:
            return False

        permissions = data.get("permissions", {})
        # User-scoped tokens behave exactly like a user's normal credentials.
        # The presence of the "user" permission takes precedence over lesser
        # permissions.
        if "user" in permissions:
            return True

        projects = permissions.get("projects")
        if projects is None:
            return False

        return self.verify_projects(projects)


class Verifier:
    def __init__(self, macaroon, context, principals, permission):
        self.macaroon = macaroon
        self.context = context
        self.principals = principals
        self.permission = permission
        self.verifier = pymacaroons.Verifier()

    def verify(self, key):
        self.verifier.satisfy_general(V1Caveat(self))

        try:
            return self.verifier.verify(self.macaroon, key)
        except pymacaroons.exceptions.MacaroonInvalidSignatureException:
            return False
