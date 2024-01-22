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

import enum
import time

from collections.abc import Sequence
from typing import Any

from pydantic import StrictInt, StrictStr, field_validator
from pymacaroons import Macaroon, Verifier
from pymacaroons.exceptions import MacaroonInvalidSignatureException
from pyramid.request import Request
from pyramid.security import Allowed

from warehouse.accounts.models import User
from warehouse.errors import WarehouseDenied
from warehouse.macaroons.caveats._core import (
    Caveat,
    CaveatError,
    Failure,
    Result,
    Success,
    as_caveat,
    deserialize,
    serialize,
)
from warehouse.oidc.interfaces import SignedClaims
from warehouse.packaging.models import Project

__all__ = ["deserialize", "serialize", "verify"]


# NOTE: Under the covers, caveat serialization is done as an array
# of `[TAG, ... fields]`, where the order of `fields` is the order of
# definition in each caveat class.
#
# This means that fields cannot be reordered or deleted, and that new
# fields *must* be added at the end of the class. New fields *must* also
# include a default value. If a change can't be made under these constraints,
# then a new Caveat class (and tag) should be created instead.


@as_caveat(tag=0)
class Expiration(Caveat, frozen=True):
    expires_at: StrictInt
    not_before: StrictInt

    def verify(self, request: Request, context: Any, permission: str) -> Result:
        now = int(time.time())
        if now < self.not_before or now >= self.expires_at:
            return Failure("token is expired")
        return Success()


@as_caveat(tag=1)
class ProjectName(Caveat, frozen=True):
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
class ProjectID(Caveat, frozen=True):
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
class RequestUser(Caveat, frozen=True):
    user_id: StrictStr

    def verify(self, request: Request, context: Any, permission: str) -> Result:
        if not isinstance(request.identity, User):
            return Failure("token with user restriction without a user")

        if str(request.identity.id) != self.user_id:
            return Failure("current user does not match user restriction in token")

        return Success()


@as_caveat(tag=4)
class OIDCPublisher(Caveat, frozen=True):
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


class PublicPermissions(enum.IntFlag, boundary=enum.FlagBoundary.STRICT):
    # We use 1 << N here instead of enum.auto() because the selected value is
    # very important to us, if the value of a permission changes, then the scope
    # of existing Macaroons will change, which would be a major security fail.
    #
    # Explicitly setting our values also means that we can skip values, allowing
    # us to reserve earlier bits for permissions that are likely going to be
    # widely used, and push less commonly used permissions to later bits.
    #
    # The structure of these values should basically always be 1 << N, where N
    # is a unique integer per permission, starting with 0 and increasing from
    # there. Effectively N is the logical ID for a given permission.

    Upload = 1 << 0


_PERMISSION_MAPPING_VERIFY = {
    # This Maps an internal permission string to our macaroon caveat permissions
    # when we're verifying a given set of permissions.
    #
    # NOTE: If an internal permission should map to multiple caveat permissions,
    #       you can use the normal bitwise operations, the most useful of which
    #       will likely be | to allow any of the listed permissions to match.
    "upload": PublicPermissions.Upload,
}


_PERMISSION_MAPPING_EMIT = {
    # Map a given internal permission string to a public permission.
    #
    # NOTE: We track this independently of the mapping for verification because
    #       a given internal permission may be valid for multiple public
    #       permissions, but that doesn't mean that we want to emit the full set
    #       of public permissions.
    #
    #       For instance, if we have internal permissions for "create project",
    #       "create release", and "upload a new file" as well as a public
    #       permission for each _and_ a overall "upload" permission that
    #       encapsulates all 3, granting someone the "upload a new file"
    #       permission shouldn't also grant the "upload" permission but both
    #       upload and "upload a new file" permission should work.
    "upload": PublicPermissions.Upload,
}


@as_caveat(tag=5)
class Permission(Caveat, frozen=True):
    permissions: PublicPermissions

    # Coerce integer to PublicPermissions, even when strict=True.
    @field_validator("permissions", mode="before")
    @classmethod
    def _coerce_int_to_public_permissions_strict(cls, value: Any) -> Any:
        if isinstance(value, int):
            return PublicPermissions(value)
        return value

    # Coerce lists of internal permission strings to PublicPermissions, which
    # let's us support Permission(permissions=["upload"]) etc.
    @field_validator("permissions", mode="before")
    @classmethod
    def _coerce_internal_to_public(cls, v):
        # If we've been given a list, we'll assume it's a list of internal
        # permissions, that we want to coerce to public permissions.
        if isinstance(v, Sequence) and not isinstance(v, str):
            # Start off with an empty set of Permissions, as we want to be
            # maximally restrictive by default, and expand the permissions to
            # the given ones.
            mapped = PublicPermissions(0)

            # Go over each permission string given, and get the mapped permission
            # set for it.
            for permission in v:
                # If we don't have any public permission mapped for a given internal
                # permission, we will just silently skip that permission, treating
                # it as if it had not been specified.
                #
                # Unmapped permissions don't have a possible value, so must either
                # be skipped or create an error, and we choose to skip to prevent
                # the need to prefilter a list of permissions.
                if (emit := _PERMISSION_MAPPING_EMIT.get(permission)) is not None:
                    mapped |= emit

            return mapped

        return v

    def verify(self, request: Request, context: Any, permission: str) -> Result:
        if (valid := _PERMISSION_MAPPING_VERIFY.get(permission)) is not None:
            # Do a binary & to determine if there is any overlap between the
            # public permissions that are embedded in this caveat, and the valid
            # public permissions for the given internal permission string.
            if self.permissions & valid:
                return Success()

        return Failure("token does not have the required permissions")


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
