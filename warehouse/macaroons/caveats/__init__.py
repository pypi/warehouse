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

from typing import Any

from pydantic import StrictInt, StrictStr
from pydantic.dataclasses import dataclass
from pymacaroons import Macaroon, Verifier
from pymacaroons.exceptions import MacaroonInvalidSignatureException
from pyramid.request import Request
from pyramid.security import Allowed

from warehouse.accounts.utils import UserContext
from warehouse.errors import WarehouseDenied
from warehouse.macaroons.caveats._core import (
    Caveat,
    CaveatError,
    Failure,
    Result,
    Success,
    as_caveat,
    deserialize,
    deserialize_obj,
    serialize,
    serialize_obj,
)
from warehouse.oidc.interfaces import SignedClaims
from warehouse.packaging.models import Project

__all__ = ["deserialize", "deserialize_obj", "serialize", "serialize_obj", "verify"]


# NOTE: Under the covers, caveat serialization is done as an array
# of `[TAG, ... fields]`, where the order of `fields` is the order of
# definition in each caveat class.
#
# This means that fields cannot be reordered or deleted, and that new
# fields *must* be added at the end of the class. New fields *must* also
# include a default value. If a change can't be made under these constraints,
# then a new Caveat class (and tag) should be created instead.


@as_caveat(tag=0)
@dataclass(frozen=True)
class Expiration(Caveat):
    expires_at: StrictInt
    not_before: StrictInt

    def verify(self, request: Request, context: Any, permission: str) -> Result:
        now = int(time.time())
        if now < self.not_before or now >= self.expires_at:
            return Failure("token is expired")
        return Success()


@as_caveat(tag=1)
@dataclass(frozen=True)
class ProjectName(Caveat):
    normalized_names: list[StrictStr]

    def verify(self, request: Request, context: Any, permission: str) -> Result:
        if not isinstance(context, Project):
            return Failure("project-scoped token used outside of a project context")

        if context.normalized_name not in self.normalized_names:
            return Failure(
                f"project-scoped token is not valid for project: {context.name!r}"
            )

        return Success()


@as_caveat(tag=2)
@dataclass(frozen=True)
class ProjectID(Caveat):
    project_ids: list[StrictStr]

    def verify(self, request: Request, context: Any, permission: str) -> Result:
        if not isinstance(context, Project):
            return Failure("project-scoped token used outside of a project context")

        if str(context.id) not in self.project_ids:
            return Failure(
                f"project-scoped token is not valid for project: {context.name!r}"
            )

        return Success()


@as_caveat(tag=3)
@dataclass(frozen=True)
class RequestUser(Caveat):
    user_id: StrictStr

    def verify(self, request: Request, context: Any, permission: str) -> Result:
        if not isinstance(request.identity, UserContext):
            return Failure("token with user restriction without a user")

        if request.identity.macaroon is None:
            return Failure("token with user restriction without a macaroon")

        if str(request.identity.user.id) != self.user_id:
            return Failure("current user does not match user restriction in token")

        return Success()


@as_caveat(tag=4)
@dataclass(frozen=True)
class OIDCPublisher(Caveat):
    oidc_publisher_id: StrictStr
    oidc_claims: SignedClaims | None = None
    """
    This field is deprecated and should not be used.

    Contains the OIDC claims passed through from token exchange.
    """

    def verify(self, request: Request, context: Any, permission: str) -> Result:
        # If the identity associated with this macaroon is not an OpenID publisher,
        # then it doesn't make sense to restrict it with an `OIDCPublisher` caveat.
        if not request.oidc_publisher:
            return Failure(
                "OIDC scoped token used outside of an OIDC identified request"
            )

        if str(request.oidc_publisher.id) != self.oidc_publisher_id:
            return Failure(
                "current OIDC publisher does not match publisher restriction in token"
            )

        # OpenID-scoped tokens are only valid against projects.
        if not isinstance(context, Project):
            return Failure("OIDC scoped token used outside of a project context")

        # Specifically, they are only valid against projects that are registered
        # to the current identifying OpenID publisher.
        if context not in request.oidc_publisher.projects:
            return Failure(
                f"OIDC scoped token is not valid for project '{context.name}'"
            )

        return Success()


def verify(
    macaroon: Macaroon, key: bytes, request: Request, context: Any, permission: str
) -> Allowed | WarehouseDenied:
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
