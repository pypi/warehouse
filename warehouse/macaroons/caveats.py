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


class InvalidMacaroonError(Exception):
    ...


class Caveat:
    def __init__(self, verifier):
        self.verifier = verifier

    def verify(self, predicate):
        raise InvalidMacaroonError

    def __call__(self, predicate):
        return self.verify(predicate)


class V1Caveat(Caveat):
    def verify_projects(self, projects):
        # First, ensure that we're actually operating in
        # the context of a package.
        if not isinstance(self.verifier.context, Project):
            raise InvalidMacaroonError(
                "project-scoped token used outside of a project context"
            )

        project = self.verifier.context
        if project.normalized_name in projects:
            return True

        raise InvalidMacaroonError(
            f"project-scoped token is not valid for project '{project.name}'"
        )

    def verify(self, predicate):
        # Already checked in TopLevelCaveat, but just in case.
        if predicate["version"] != 1:
            raise InvalidMacaroonError("invalid version for this macaroon")

        permissions = predicate.get("permissions")
        if permissions is None:
            raise InvalidMacaroonError("invalid permissions in predicate")

        if permissions == "user":
            # User-scoped tokens behave exactly like a user's normal credentials.
            return True

        projects = permissions.get("projects")
        if projects is None:
            raise InvalidMacaroonError("invalid projects in predicate")

        return self.verify_projects(projects)


class V2Caveat(Caveat):
    def verify(self, predicate):
        # Already checked in TopLevelCaveat, but just in case.
        if predicate["version"] != 2:
            raise InvalidMacaroonError("invalid version for this macaroon")

        raise InvalidMacaroonError("not supported yet")


class TopLevelCaveat(Caveat):
    def verify(self, predicate):
        try:
            data = json.loads(predicate)
            version = data["version"]
        except (ValueError, KeyError, TypeError):
            raise InvalidMacaroonError("malformed predicate")

        if version == 1:
            caveat_verifier = V1Caveat(self.verifier)
        elif version == 2:
            caveat_verifier = V2Caveat(self.verifier)
        else:
            raise InvalidMacaroonError("invalid version: must be 1 or 2")

        return caveat_verifier.verify(data)


class Verifier:
    def __init__(self, macaroon, context, principals, permission):
        self.macaroon = macaroon
        self.context = context
        self.principals = principals
        self.permission = permission
        self.verifier = pymacaroons.Verifier()

    def verify(self, key):
        self.verifier.satisfy_general(TopLevelCaveat(self))

        try:
            return self.verifier.verify(self.macaroon, key)
        except (
            pymacaroons.exceptions.MacaroonInvalidSignatureException,
            Exception,  # https://github.com/ecordell/pymacaroons/issues/50
        ):
            raise InvalidMacaroonError("invalid macaroon signature")
