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

from dataclasses import dataclass
from typing import Any

from pymacaroons import Macaroon, Verifier
from pymacaroons.exceptions import MacaroonInvalidSignatureException
from pyramid.request import Request
from pyramid.security import Allowed

from warehouse.accounts.models import User
from warehouse.errors import WarehouseDenied
from warehouse.macaroons.caveats._core import (
    Caveat,
    CaveatError,
    Result,
    Success,
    Failure,
    as_caveat,
    deserialize,
    serialize,
)
from warehouse.packaging.models import Project


__all__ = ["InvalidMacaroonError", "deserialize", "serialize", "verify"]


class InvalidMacaroonError(Exception):
    ...


@as_caveat(tag=0)
@dataclass(frozen=True, slots=True, kw_only=True)
class Expiration(Caveat):
    expires_at: int
    not_before: int

    def verify(self, request: Request, context: Any, permission: str) -> Result:
        now = int(time.time())
        if now < self.not_before or now >= self.expires_at:
            return Failure("token is expired")
        return Success()


@as_caveat(tag=1)
@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectName(Caveat):
    normalized_names: list[str]

    def verify(self, request: Request, context: Any, permission: str) -> Result:
        if not isinstance(context, Project):
            return Failure("project-scoped toekn used outside of a project context")

        if context.normalized_name not in self.normalized_names:
            return Failure(
                f"project-scoped token is not valid for project: {context.name!r}"
            )

        return Success()


@as_caveat(tag=2)
@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectID(Caveat):
    project_ids: list[str]

    def verify(self, request: Request, context: Any, permission: str) -> Result:
        if not isinstance(context, Project):
            return Failure("project-scoped token used outside of a project context")

        if str(context.id) not in self.project_ids:
            return Failure(
                f"project-scoped token is not valid for project: {context.name!r}"
            )

        return Success()


@as_caveat(tag=3)
@dataclass(frozen=True, slots=True, kw_only=True)
class RequestUser(Caveat):
    user_id: str

    def verify(self, request: Request, context: Any, permission: str) -> Result:
        if not isinstance(request.identity, User):
            return Failure("token with user restriction used without a user")

        if str(request.identity.id) != self.user_id:
            return Failure(f"current user does not match user restriction in token")

        return Success()


def verify(
    macaroon: Macaroon, key: bytes, request: Request, context: Any, permission: str
) -> bool:
    errors: list[str] = []

    def _verify_caveat(predicate: bytes):
        try:
            caveat = deserialize(predicate)
        except CaveatError as exc:
            errors.append(str(exc))
            return False

        result = caveat.verify(request, context, permission)
        assert isinstance(result, (Success, Failure))

        if isinstance(result, Failure):
            errors.append(result.reason)
            return False

        return True

    verifier = Verifier()
    verifier.satisfy_general(_verify_caveat)

    result = False
    try:
        result = verifier.verify(macaroon, key)
    except (
        MacaroonInvalidSignatureException,
        Exception,  # https://github.com/ecordell/pymacaroons/issues/50
    ) as exc:
        if errors:
            return WarehouseDenied(", ".join(errors), reason="invalid_api_token")
        elif isinstance(exc, MacaroonInvalidSignatureException):
            return WarehouseDenied(
                "signatures do not match", reason="invalid_api_token"
            )

    if not result:
        return WarehouseDenied("unknown error", reason="invalid_api_token")
    return Allowed("signature and caveats OK")
