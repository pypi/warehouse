# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Self, TypedDict, TypeVar, Unpack

import rfc3986
import sentry_sdk

from sqlalchemy import ForeignKey, Index, String, func, orm
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from warehouse import db
from warehouse.oidc.errors import InvalidPublisherError, ReusedTokenError
from warehouse.oidc.interfaces import SignedClaims
from warehouse.oidc.urls import verify_url_from_reference

if TYPE_CHECKING:
    from pypi_attestations import Publisher

    from warehouse.accounts.models import User
    from warehouse.macaroons.models import Macaroon
    from warehouse.oidc.services import OIDCPublisherService
    from warehouse.packaging.models import Project


C = TypeVar("C")


class CheckNamedArguments(TypedDict, total=False):
    publisher_service: OIDCPublisherService


CheckClaimCallable = Callable[[C, C, SignedClaims, Unpack[CheckNamedArguments]], bool]


def check_claim_binary(binary_func: Callable[[C, C], bool]) -> CheckClaimCallable[C]:
    """
    Wraps a binary comparison function so that it takes three arguments instead,
    ignoring the third.

    This is used solely to make claim verification compatible with "trivial"
    comparison checks like `str.__eq__`.
    """

    def wrapper(
        ground_truth: C,
        signed_claim: C,
        _all_signed_claims: SignedClaims,
        **_kwargs: Unpack[CheckNamedArguments],
    ) -> bool:
        return binary_func(ground_truth, signed_claim)

    return wrapper


def check_claim_invariant(value: C) -> CheckClaimCallable[C]:
    """
    Wraps a fixed value comparison into a three-argument function.

    This is used solely to make claim verification compatible with "invariant"
    comparison checks, like "claim x is always the literal `true` value".
    """

    def wrapper(
        ground_truth: C,
        signed_claim: C,
        _all_signed_claims: SignedClaims,
        **_kwargs: Unpack[CheckNamedArguments],
    ):
        return ground_truth == signed_claim == value

    return wrapper


def check_existing_jti(
    _ground_truth,
    signed_claim,
    _all_signed_claims,
    **kwargs: Unpack[CheckNamedArguments],
) -> bool:
    """Returns True if the checks passes or raises an exception."""

    publisher_service: OIDCPublisherService = kwargs["publisher_service"]

    if publisher_service.jwt_identifier_exists(signed_claim):
        publisher_service.metrics.increment(
            "warehouse.oidc.reused_token",
            tags=[f"publisher:{publisher_service.publisher}"],
        )
        raise ReusedTokenError()

    return True


class OIDCPublisherProjectAssociation(db.Model):
    __tablename__ = "oidc_publisher_project_association"

    oidc_publisher_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("oidc_publishers.id"),
        nullable=False,
        primary_key=True,
    )
    project_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )


class OIDCPublisherMixin:
    """
    A mixin for common functionality between all OIDC publishers, including
    "pending" publishers that don't correspond to an extant project yet.
    """

    # Each hierarchy of OIDC publishers (both `OIDCPublisher` and
    # `PendingOIDCPublisher`) use a `discriminator` column for model
    # polymorphism, but the two are not mutually polymorphic at the DB level.
    discriminator = mapped_column(String)

    # A map of claim names to "check" functions, each of which
    # has the signature `check(ground-truth, signed-claim, all-signed-claims) -> bool`.
    __required_verifiable_claims__: dict[str, CheckClaimCallable[Any]] = dict()

    # A set of claim names which must be present, but can't be verified
    __required_unverifiable_claims__: set[str] = set()

    # Simlar to __verificable_claims__, but these claims are optional
    __optional_verifiable_claims__: dict[str, CheckClaimCallable[Any]] = dict()

    # Claims that have already been verified during the JWT signature
    # verification phase if present.
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

    # Individual publishers can have complex unique constraints on their
    # required and optional attributes, and thus can't be naively looked
    # up from a raw claim set.
    #
    # Each subclass should explicitly override this method, which takes
    # a set of claims (`SignedClaims`) and returns a Publisher.
    # In case that multiple publishers satisfy the given claims, the
    # most specific publisher should be the one returned, i.e. the one with
    # the most optional constraints satisfied.
    #
    @classmethod
    def lookup_by_claims(cls, session, signed_claims: SignedClaims) -> Self:
        raise NotImplementedError

    @classmethod
    def all_known_claims(cls) -> set[str]:
        """
        Returns all claims "known" to this publisher.
        """
        return (
            cls.__required_verifiable_claims__.keys()
            | cls.__required_unverifiable_claims__
            | cls.__optional_verifiable_claims__.keys()
            | cls.__preverified_claims__
            | cls.__unchecked_claims__
        )

    @classmethod
    def check_claims_existence(cls, signed_claims: SignedClaims) -> None:
        """
        Raises an error if any of the required claims for a Publisher is missing from
        `signed_claims`.

        This is used to check if required claims are missing from the token. If so,
        an error is logged since this is likely a bug from the OIDC provider that
        generated the token. Unexpected claims are logged as warnings that the JWT
        payload has changed.
        """

        # Defensive programming: treat the absence of any claims to verify
        # as a failure rather than trivially valid.
        if not cls.__required_verifiable_claims__:
            raise InvalidPublisherError("No required verifiable claims")

        # All claims should be accounted for.
        # The presence of an unaccounted claim is not an error, only a warning
        # that the JWT payload has changed.
        unaccounted_claims = sorted(list(signed_claims.keys() - cls.all_known_claims()))
        if unaccounted_claims:
            with sentry_sdk.new_scope() as scope:
                scope.fingerprint = unaccounted_claims
                sentry_sdk.capture_message(
                    f"JWT for {cls.__name__} has unaccounted claims: "
                    f"{unaccounted_claims}"
                )

        # Verify that all required claims are present.
        for claim_name in (
            cls.__required_verifiable_claims__.keys()
            | cls.__required_unverifiable_claims__
        ):
            # All required claims are mandatory. The absence of a missing
            # claim *is* an error with the JWT, since it indicates a breaking
            # change in the JWT's payload.
            signed_claim = signed_claims.get(claim_name)
            if signed_claim is None:
                with sentry_sdk.new_scope() as scope:
                    scope.fingerprint = [claim_name]
                    sentry_sdk.capture_message(
                        f"JWT for {cls.__name__} is missing claim: {claim_name}"
                    )
                raise InvalidPublisherError(f"Missing claim {claim_name!r}")

    def verify_claims(
        self, signed_claims: SignedClaims, publisher_service: OIDCPublisherService
    ):
        """
        Given a JWT that has been successfully decoded (checked for a valid
        signature and basic claims), verify it against the more specific
        claims of this publisher.
        """

        # All required claims should be present, since this is checked during Publisher
        # lookup. Now we verify each verifiable claim is correct.
        for claim_name, check in self.__required_verifiable_claims__.items():
            signed_claim = signed_claims.get(claim_name)
            if not check(
                getattr(self, claim_name),
                signed_claim,
                signed_claims,
                publisher_service=publisher_service,
            ):
                raise InvalidPublisherError(
                    f"Check failed for required claim {claim_name!r}"
                )

        # Check optional verifiable claims
        for claim_name, check in self.__optional_verifiable_claims__.items():
            # All optional claims are optional. The absence of a missing
            # claim is *NOT* an error with the JWT, however we should still
            # verify this against the check, because the claim might be
            # required for a given publisher.
            signed_claim = signed_claims.get(claim_name)

            if not check(
                getattr(self, claim_name),
                signed_claim,
                signed_claims,
                publisher_service=publisher_service,
            ):
                raise InvalidPublisherError(
                    f"Check failed for optional claim {claim_name!r}"
                )

        return True

    @property
    def publisher_name(self) -> str:  # pragma: no cover
        # Only concrete subclasses are constructed.
        raise NotImplementedError

    @property
    def publisher_base_url(self) -> str | None:  # pragma: no cover
        # Only concrete subclasses are constructed.
        raise NotImplementedError

    def publisher_url(
        self, claims: SignedClaims | None = None
    ) -> str | None:  # pragma: no cover
        """
        NOTE: This is **NOT** a `@property` because we pass `claims` to it.
        When calling, make sure to use `publisher_url()`
        """
        # Only concrete subclasses are constructed.
        raise NotImplementedError

    @property
    def attestation_identity(self) -> Publisher | None:
        """
        Returns an appropriate attestation verification identity, if this
        kind of publisher supports attestations.

        Concrete subclasses should override this upon adding attestation support.
        """
        return None

    def stored_claims(
        self, claims: SignedClaims | None = None
    ) -> dict:  # pragma: no cover
        """
        These are claims that are serialized into any macaroon generated for
        this publisher. You likely want to use this to surface claims that
        are not configured on the publishers, that might vary from one publish
        event to the next, and are useful to show to the user.

        NOTE: This is **NOT** a `@property` because we pass `claims` to it.
        When calling, make sure to use `stored_claims()`
        """
        # Only concrete subclasses are constructed.
        raise NotImplementedError

    def verify_url(self, url: str) -> bool:
        """
        Verify a given URL against this Trusted Publisher's base URL

        A URL is considered "verified" iff it matches the Trusted Publisher URL
        such that, when both URLs are normalized:
        - The scheme component is the same (e.g: both use `https`)
        - The authority component is the same (e.g.: `github.com`)
        - The path component is the same, or a sub-path of the Trusted Publisher URL
          (e.g.: `org/project` and `org/project/issues.html` will pass verification
          against an `org/project` Trusted Publisher path component)
        - The path component of the Trusted Publisher URL is not empty
        Note: We compare the authority component instead of the host component because
        the authority includes the host, and in practice neither URL should have user
        nor port information.
        """
        if self.publisher_base_url is None:
            # Currently this only applies to the Google provider
            return False
        publisher_uri = rfc3986.api.uri_reference(self.publisher_base_url).normalize()
        if publisher_uri.path is None:
            # Currently no Trusted Publishers with a `publisher_base_url` have an empty
            # path component, so we defensively fail verification.
            return False
        return verify_url_from_reference(
            reference_url=self.publisher_base_url,
            url=url,
        )

    def exists(self, session) -> bool:  # pragma: no cover
        """
        Check if the publisher exists in the database
        """
        # Only concrete subclasses are constructed.
        raise NotImplementedError


class OIDCPublisher(OIDCPublisherMixin, db.Model):
    __tablename__ = "oidc_publishers"

    projects: Mapped[list[Project]] = orm.relationship(
        secondary=OIDCPublisherProjectAssociation.__table__,
        back_populates="oidc_publishers",
    )
    macaroons: Mapped[list[Macaroon]] = orm.relationship(
        cascade="all, delete-orphan", lazy=True
    )

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

    project_name = mapped_column(String, nullable=False)
    added_by_id = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    added_by: Mapped[User] = orm.relationship(back_populates="pending_oidc_publishers")

    __table_args__ = (
        Index(
            "pending_project_name_ultranormalized",
            func.ultranormalize_name(project_name),
        ),
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
