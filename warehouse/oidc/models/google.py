# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import typing

from typing import Any, Self
from uuid import UUID

from more_itertools import first_true
from pypi_attestations import GooglePublisher as GoogleIdentity, Publisher
from sqlalchemy import ForeignKey, String, UniqueConstraint, and_, exists
from sqlalchemy.orm import Mapped, Query, mapped_column

from warehouse.oidc.errors import InvalidPublisherError
from warehouse.oidc.interfaces import SignedClaims
from warehouse.oidc.models._core import (
    CheckClaimCallable,
    OIDCPublisher,
    PendingOIDCPublisher,
    check_claim_binary,
    check_claim_invariant,
)

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session


GOOGLE_OIDC_ISSUER_URL = "https://accounts.google.com"


def _check_sub(
    ground_truth: str,
    signed_claim: str,
    _all_signed_claims: SignedClaims,
    **_kwargs,
) -> bool:
    # If we haven't set a subject for the publisher, we don't need to check
    # this claim.
    if ground_truth == "":
        return True

    # Defensive: Google should never send us an empty or null subject, but
    # we check regardless.
    if not signed_claim:
        return False

    return ground_truth == signed_claim


class GooglePublisherMixin:
    """
    Common functionality for both pending and concrete Google OIDC
    providers.
    """

    email: Mapped[str] = mapped_column(String, nullable=False)
    sub: Mapped[str] = mapped_column(String, nullable=True)

    __required_verifiable_claims__: dict[str, CheckClaimCallable[Any]] = {
        "email": check_claim_binary(str.__eq__),
        "email_verified": check_claim_invariant(True),
    }

    __optional_verifiable_claims__: dict[str, CheckClaimCallable[Any]] = {
        "sub": _check_sub
    }

    __unchecked_claims__ = {"azp", "google"}

    @classmethod
    def lookup_by_claims(cls, session: Session, signed_claims: SignedClaims) -> Self:
        query: Query = Query(cls).filter_by(email=signed_claims["email"])
        publishers = query.with_session(session).all()

        if sub := signed_claims.get("sub"):
            if specific_publisher := first_true(
                publishers, pred=lambda p: p.sub == sub
            ):
                return specific_publisher

        if general_publisher := first_true(publishers, pred=lambda p: p.sub == ""):
            return general_publisher

        raise InvalidPublisherError("Publisher with matching claims was not found")

    @property
    def publisher_name(self) -> str:
        return "Google"

    @property
    def publisher_base_url(self) -> None:
        return None

    def publisher_url(self, claims: SignedClaims | None = None) -> None:
        return None

    @property
    def attestation_identity(self) -> Publisher | None:
        return GoogleIdentity(email=self.email)

    def stored_claims(self, claims: SignedClaims | None = None) -> dict:
        return {}

    @property
    def email_verified(self) -> bool:
        # We don't consider a claim set valid unless `email_verified` is true;
        # no other states are possible.
        return True

    def __str__(self) -> str:
        return self.email

    def exists(self, session: Session) -> bool:
        return session.query(
            exists().where(
                and_(
                    self.__class__.email == self.email,
                    self.__class__.sub == self.sub,
                )
            )
        ).scalar()

    @property
    def admin_details(self) -> list[tuple[str, str]]:
        """Returns Google publisher configuration details for admin display."""
        details = [
            ("Email", self.email),
        ]
        if self.sub:
            details.append(("Subject", self.sub))
        return details


class GooglePublisher(GooglePublisherMixin, OIDCPublisher):
    __tablename__ = "google_oidc_publishers"
    __mapper_args__ = {"polymorphic_identity": "google_oidc_publishers"}
    __table_args__ = (
        UniqueConstraint(
            "email",
            "sub",
            name="_google_oidc_publisher_uc",
        ),
    )

    id: Mapped[UUID] = mapped_column(ForeignKey(OIDCPublisher.id), primary_key=True)


class PendingGooglePublisher(GooglePublisherMixin, PendingOIDCPublisher):
    __tablename__ = "pending_google_oidc_publishers"
    __mapper_args__ = {"polymorphic_identity": "pending_google_oidc_publishers"}
    __table_args__ = (  # type: ignore[assignment]
        UniqueConstraint(
            "email",
            "sub",
            name="_pending_google_oidc_publisher_uc",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        ForeignKey(PendingOIDCPublisher.id), primary_key=True
    )

    def reify(self, session: Session) -> GooglePublisher:
        """
        Returns a `GooglePublisher` for this `PendingGooglePublisher`,
        deleting the `PendingGooglePublisher` in the process.
        """

        maybe_publisher = (
            session.query(GooglePublisher)
            .filter(
                GooglePublisher.email == self.email,
                GooglePublisher.sub == self.sub,
            )
            .one_or_none()
        )

        publisher = maybe_publisher or GooglePublisher(
            email=self.email,
            sub=self.sub,
        )

        session.delete(self)
        return publisher
