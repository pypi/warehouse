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

from pyramid.security import Allowed

from warehouse.errors import WarehouseDenied
from warehouse.oidc import models as oidc_models
from warehouse.packaging.models import Project


class InvalidMacaroonError(Exception):
    ...


class Caveat:
    def __init__(self, verifier):
        self.verifier = verifier
        # TODO: Surface this failure reason to the user.
        # See: https://github.com/pypi/warehouse/issues/9018
        self.failure_reason = None

    def verify(self, predicate) -> bool:
        return False

    def __call__(self, predicate):
        return self.verify(predicate)


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
            version = data["version"]
            permissions = data["permissions"]
        except (KeyError, ValueError, TypeError):
            return False

        if version != 1:
            return False

        if permissions is None:
            return False

        if permissions == "user":
            # User-scoped tokens behave exactly like a user's normal credentials.
            return True

        if permissions == "oidc":
            # OIDC-scoped tokens behave as if they're scoped for every project
            # that the corresponding OIDC provider is registered against.
            if not isinstance(self.verifier.identity, oidc_models.OIDCProvider):
                self.failure_reason = (
                    "OIDC-scoped token used outside of an OIDC identity context"
                )
                return False

            projects = [p.normalized_name for p in self.verifier.identity.projects]
            return self.verify_projects(projects)

        if not isinstance(permissions, dict):
            self.failure_reason = "invalid permissions format"
            return False

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
            return False

        return True


class Verifier:
    def __init__(self, macaroon, context, principals, permission, identity):
        self.macaroon = macaroon
        self.context = context
        self.principals = principals
        self.permission = permission
        self.identity = identity
        self.verifier = pymacaroons.Verifier()

    def verify(self, key):
        self.verifier.satisfy_general(V1Caveat(self))
        self.verifier.satisfy_general(ExpiryCaveat(self))
        self.verifier.satisfy_general(ProjectIDsCaveat(self))

        try:
            result = self.verifier.verify(self.macaroon, key)
        except pymacaroons.exceptions.MacaroonInvalidSignatureException as exc:
            failure_reasons = []
            for cb in self.verifier.callbacks:
                failure_reason = getattr(cb, "failure_reason", None)
                if failure_reason is not None:
                    failure_reasons.append(failure_reason)

            # If we have a more detailed set of failure reasons, use them.
            # Otherwise, use whatever the exception gives us.
            if len(failure_reasons) > 0:
                return WarehouseDenied(
                    ", ".join(failure_reasons), reason="invalid_api_token"
                )
            else:
                return WarehouseDenied(str(exc), reason="invalid_api_token")
        except Exception:
            # The pymacaroons `verify` API with leak exceptions raised during caveat
            # verification, which *normally* indicate a deserialization error
            # (i.e., a malformed caveat body).
            # When this happens, we don't want to display a random stringified
            # Python exception to the user, so instead we emit a generic error.
            # See https://github.com/ecordell/pymacaroons/issues/50
            return WarehouseDenied("malformed macaroon", reason="invalid_api_token")

        # NOTE: We should never hit this case, since pymacaroons *should* always either
        # raise on failure *or* return true. But there's nothing stopping that from
        # silently breaking in the future, so we check the result defensively here.
        if not result:
            return WarehouseDenied("unknown error", reason="invalid_api_token")
        else:
            return Allowed("signature and caveats OK")
