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

from warehouse.packaging.models import Project, Release

from datetime import datetime

from datetime import timedelta

import pytz

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

        for user_proj in projects:
            if project.normalized_name == user_proj.get("project-name"):
                return True
        raise InvalidMacaroon("project-scoped token matches no projects")
    
    def verify_releases(self, release):
        project = self.verifier.context

        for version in project.all_versions:
            if release == version[0]:
                raise InvalidMacaroon("release already exists")
        return True
    
    def verify_expiration(self, expiration):
        try:
            expiration = datetime.strptime(expiration, "%Y-%m-%dT%H:%M")
        except ValueError:
            raise InvalidMacaroon("invalid expiration")

        d = datetime.now()
        tz = pytz.timezone('GMT') # GMT for POC, ideally would be user's local timezone
        tz_aware = tz.localize(d)
        expiration_aware = tz.localize(expiration)
        if expiration_aware < tz_aware:
            raise InvalidMacaroon("time has expired")

        return True

    def verify(self, predicate):
        try:
            data = json.loads(predicate)
        except ValueError:
            raise InvalidMacaroon(f"malformatted predicate {predicate}")

        if data.get("version") != 1:
            raise InvalidMacaroon("invalid version in predicate")

        permissions = data.get("permissions")
        if permissions is None:
            raise InvalidMacaroon("invalid permissions in predicate")

        if permissions.get("scope") == "user":
            if permissions.get("expiration") is None:
                raise InvalidMacaroon("invalid expiration in predicate")
            else:
                self.verify_expiration(permissions.get("expiration"))
            return True

        projects = permissions.get("projects")
        if projects is None:
            raise InvalidMacaroon("invalid projects in predicate")
        else:
            self.verify_projects(projects)

        for project in projects:
            release = project.get("version")
            if release is None:
                raise InvalidMacaroon("invalid release in predicate")
            else:
                self.verify_releases(release)

        expiration = permissions.get("expiration")
        if expiration is None:
            raise InvalidMacaroon("invalid expiration in predicate")
        else:
            self.verify_expiration(expiration)

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

        try:
            return self.verifier.verify(self.macaroon, key)
        except pymacaroons.exceptions.MacaroonInvalidSignatureException:
            raise InvalidMacaroon("invalid macaroon signature")