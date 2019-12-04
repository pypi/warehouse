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

from datetime import datetime, timezone

import pymacaroons

from warehouse.packaging.models import Project


class InvalidMacaroon(Exception):
    ...


class Caveat:
    def __init__(self, verifier):
        self.verifier = verifier

    def verify(self, predicate):
        raise InvalidMacaroon

    def __call__(self, predicate):
        return self.verify(predicate)


class V1Caveat(Caveat):
    def verify_projects(self, projects):
        # First, ensure that we're actually operating in
        # the context of a package.
        if not isinstance(self.verifier.context, Project):
            raise InvalidMacaroon(
                "project-scoped token used outside of a project context"
            )

        project = self.verifier.context
        if project.normalized_name in projects:
            return True

        raise InvalidMacaroon("project-scoped token matches no projects")

    def verify(self, predicate):
        permissions = predicate.get("permissions")
        if permissions is None:
            raise InvalidMacaroon("invalid permissions in predicate")

        if permissions == "user":
            # User-scoped tokens behave exactly like a user's normal credentials.
            return True

        projects = permissions.get("projects")
        if projects is None:
            raise InvalidMacaroon("invalid projects in predicate")
        else:
            self.verify_projects(projects)

        return True


class V2Caveat(Caveat):
    def verify_expiration(self, expiration):
        now = int(datetime.now(tz=timezone.utc).timestamp())
        if expiration < now:
            raise InvalidMacaroon("token has expired")

        return True

    def verify_version(self, version):
        project = self.verifier.context

        for extant_version in project.all_versions:
            if version == extant_version[0]:
                raise InvalidMacaroon("release already exists")
        return True

    def verify_projects(self, projects):
        # First, ensure that we're actually operating in
        # the context of a package.
        if not isinstance(self.verifier.context, Project):
            raise InvalidMacaroon(
                "project-scoped token used outside of a project context"
            )

        project = self.verifier.context

        for proj in projects:
            if proj["name"] == project.normalized_name:
                version = proj.get("version")
                if version is not None:
                    self.verify_version(version)
                return True

        raise InvalidMacaroon("project-scoped token matches no projects")

    def verify(self, predicate):
        expiration = predicate.get("expiration")
        if expiration is not None:
            self.verify_expiration(expiration)

        permissions = predicate.get("permissions")
        if permissions is None:
            raise InvalidMacaroon("invalid permissions in predicate")

        if permissions == "user":
            # User-scoped tokens behave exactly like a user's normal credentials.
            return True

        projects = permissions.get("projects")
        if projects is None:
            raise InvalidMacaroon("invalid projects in predicate")
        self.verify_projects(projects)

        return True


class TopLevelCaveat(Caveat):
    def verify(self, predicate):
        try:
            data = json.loads(predicate)
        except ValueError:
            raise InvalidMacaroon("malformed predicate")

        version = data.get("version")
        if version is None:
            raise InvalidMacaroon("malformed version")

        if version == 1:
            caveat_verifier = V1Caveat(self.verifier)
        elif version == 2:
            caveat_verifier = V2Caveat(self.verifier)
        else:
            raise InvalidMacaroon("invalid version")

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
        except pymacaroons.exceptions.MacaroonInvalidSignatureException:
            raise InvalidMacaroon("invalid macaroon signature")
