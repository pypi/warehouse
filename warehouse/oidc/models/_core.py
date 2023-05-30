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

from collections.abc import Callable
from typing import Any

import sentry_sdk

from sqlalchemy import Column, ForeignKey, String, orm
from sqlalchemy.dialects.postgresql import UUID

from warehouse import db
from warehouse.macaroons.models import Macaroon
from warehouse.oidc.interfaces import SignedClaims
from warehouse.packaging.models import Project


def _check_claim_binary(binary_func):
    """
    Wraps a binary comparison function so that it takes three arguments instead,
    ignoring the third.

    This is used solely to make claim verification compatible with "trivial"
    comparison checks like `str.__eq__`.
    """

    def wrapper(ground_truth, signed_claim, all_signed_claims):
        return binary_func(ground_truth, signed_claim)

    return wrapper


def _check_claim_invariant(value: Any):
    """
    Wraps a fixed value comparison into a three-argument function.

    This is used solely to make claim verification compatible with "invariant"
    comparison checks, like "claim x is always the literal `true` value".
    """

    def wrapper(ground_truth, signed_claim, all_signed_claims):
        return ground_truth == signed_claim == value

    return wrapper


class OIDCPublisherProjectAssociation(db.Model):
    __tablename__ = "oidc_publisher_project_association"

    oidc_publisher_id = Column(
        UUID(as_uuid=True),
        ForeignKey("oidc_publishers.id"),
        nullable=False,
        primary_key=True,
    )
    project_id = Column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, primary_key=True
    )


class OIDCPublisherMixin:
    """
    A mixin for common functionality between all OIDC publishers, including
    "pending" publishers that don't correspond to an extant project yet.
    """

    # Each hierarchy of OIDC publishers (both `OIDCPublisher` and
    # `PendingOIDCPublisher`) use a `discriminator` column for model
    # polymorphism, but the two are not mutually polymorphic at the DB level.
    discriminator = Column(String)

    # A map of claim names to "check" functions, each of which
    # has the signature `check(ground-truth, signed-claim, all-signed-claims) -> bool`.
    __required_verifiable_claims__: dict[
        str, Callable[[Any, Any, dict[str, Any]], bool]
    ] = dict()

    # Simlar to __verificable_claims__, but these claims are optional
    __optional_verifiable_claims__: dict[
        str, Callable[[Any, Any, dict[str, Any]], bool]
    ] = dict()

    # Claims that have already been verified during the JWT signature
    # verification phase.
    __preverified_claims__ = {
        "iss",
        "iat",
        "nbf",
        "exp",
        "aud",
    }

    # Individual publishers should explicitly override this set,
    # indicating any custom claims that are known to be present but are
    # not checked as part of verifying the JWT.
    __unchecked_claims__: set[str] = set()

    @classmethod
    def all_known_claims(cls):
        """
        Returns all claims "known" to this publisher.
        """
        return (
            cls.__required_verifiable_claims__.keys()
            | cls.__optional_verifiable_claims__.keys()
            | cls.__preverified_claims__
            | cls.__unchecked_claims__
        )

    def verify_claims(self, signed_claims: SignedClaims):
        """
        Given a JWT that has been successfully decoded (checked for a valid
        signature and basic claims), verify it against the more specific
        claims of this publisher.
        """

        # Defensive programming: treat the absence of any claims to verify
        # as a failure rather than trivially valid.
        if not self.__required_verifiable_claims__:
            return False

        # All claims should be accounted for.
        # The presence of an unaccounted claim is not an error, only a warning
        # that the JWT payload has changed.
        unaccounted_claims = sorted(
            list(signed_claims.keys() - self.all_known_claims())
        )
        if unaccounted_claims:
            with sentry_sdk.push_scope() as scope:
                scope.fingerprint = unaccounted_claims
                sentry_sdk.capture_message(
                    f"JWT for {self.__class__.__name__} has unaccounted claims: "
                    f"{unaccounted_claims}"
                )

        # Finally, perform the actual claim verification.
        for claim_name, check in self.__required_verifiable_claims__.items():
            # All required claims are mandatory. The absence of a missing
            # claim *is* an error with the JWT, since it indicates a breaking
            # change in the JWT's payload.
            signed_claim = signed_claims.get(claim_name)
            if signed_claim is None:
                with sentry_sdk.push_scope() as scope:
                    scope.fingerprint = [claim_name]
                    sentry_sdk.capture_message(
                        f"JWT for {self.__class__.__name__} is missing claim: "
                        f"{claim_name}"
                    )
                return False

            if not check(getattr(self, claim_name), signed_claim, signed_claims):
                return False

        # Check optional verifiable claims
        for claim_name, check in self.__optional_verifiable_claims__.items():
            # All optional claims are optional. The absence of a missing
            # claim is *NOT* an error with the JWT, however we should still
            # verify this against the check, because the claim might be
            # required for a given publisher.
            signed_claim = signed_claims.get(claim_name)

            if not check(getattr(self, claim_name), signed_claim, signed_claims):
                return False

        return True

    @property
    def publisher_name(self):  # pragma: no cover
        # Only concrete subclasses are constructed.
        raise NotImplementedError

    def publisher_url(self, claims=None):  # pragma: no cover
        # Only concrete subclasses are constructed.
        raise NotImplementedError


class OIDCPublisher(OIDCPublisherMixin, db.Model):
    __tablename__ = "oidc_publishers"

    projects = orm.relationship(
        Project,
        secondary=OIDCPublisherProjectAssociation.__table__,  # type: ignore
        backref="oidc_publishers",
    )
    macaroons = orm.relationship(Macaroon, cascade="all, delete-orphan", lazy=True)

    __mapper_args__ = {
        "polymorphic_identity": "oidc_publishers",
        "polymorphic_on": OIDCPublisherMixin.discriminator,
    }


class PendingOIDCPublisher(OIDCPublisherMixin, db.Model):
    """
    A "pending" OIDC publisher, i.e. one that's been registered by a user
    but doesn't correspond to an existing PyPI project yet.
    """

    __tablename__ = "pending_oidc_publishers"

    project_name = Column(String, nullable=False)
    added_by_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    __mapper_args__ = {
        "polymorphic_identity": "pending_oidc_publishers",
        "polymorphic_on": OIDCPublisherMixin.discriminator,
    }

    def reify(self, session):  # pragma: no cover
        """
        Return an equivalent "normal" OIDC publisher model for this pending publisher,
        deleting the pending publisher in the process.
        """

        # Only concrete subclasses are constructed.
        raise NotImplementedError
