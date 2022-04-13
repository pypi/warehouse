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

import pymacaroons

from warehouse.packaging.models import Project


class InvalidMacaroonError(Exception):
    ...


class Caveat:
    def __init__(self, verifier):
        self.verifier = verifier
        self.failure_reason = None

    def _fail(self, reason):
        # TODO: Surface this failure reason to the user.
        # See: https://github.com/pypa/warehouse/issues/9018
        self.failure_reason = reason
        return False

    def verify(self, predicate):
        return self._fail("programming error")

    def __call__(self, predicate):
        return self.verify(predicate)


class V1Caveat(Caveat):
    def verify_projects(self, projects):
        # First, ensure that we're actually operating in
        # the context of a package.
        if not isinstance(self.verifier.context, Project):
            return self._fail("project-scoped token used outside of a project context")

        project = self.verifier.context
        if project.normalized_name in projects:
            return True

        return self._fail(
            f"project-scoped token is not valid for project '{project.name}'"
        )

    def verify(self, predicate):
        try:
            data = json.loads(predicate)
        except ValueError:
            return self._fail("malformatted predicate")

        if data.get("version") != 1:
            return self._fail("invalid version in predicate")

        permissions = data.get("permissions")
        if permissions is None:
            return self._fail("invalid permissions in predicate")

        if permissions == "user":
            # User-scoped tokens behave exactly like a user's normal credentials.
            return True

        projects = permissions.get("projects")
        if projects is None:
            return self._fail("invalid projects in predicate")

        return self.verify_projects(projects)


class ExpiryCaveat(Caveat):
    def verify(self, predicate):
        try:
            data = json.loads(predicate)
            expiry = data["exp"]
            not_before = data["nbf"]
        except (KeyError, ValueError, TypeError):
            return False

        if not expiry or not not_before:
            return False

        now = int(time.time())
        if now < not_before or now >= expiry:
            return False

        return True


class Verifier:
    def __init__(self, macaroon, context, principals, permission):
        self.macaroon = macaroon
        self.context = context
        self.principals = principals
        self.permission = permission
        self.verifier = pymacaroons.Verifier()

    def verify(self, key):
        self.verifier.satisfy_general(V1Caveat(self))
        self.verifier.satisfy_general(ExpiryCaveat(self))

        try:
            return self.verifier.verify(self.macaroon, key)
        except (
            pymacaroons.exceptions.MacaroonInvalidSignatureException,
            Exception,  # https://github.com/ecordell/pymacaroons/issues/50
        ):
            return False
