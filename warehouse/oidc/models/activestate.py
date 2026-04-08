# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import typing
import urllib

from typing import Any, Self
from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint, and_, exists
from sqlalchemy.orm import Mapped, Query, mapped_column

import warehouse.oidc.models._core as oidccore

from warehouse.oidc.errors import InvalidPublisherError
from warehouse.oidc.interfaces import SignedClaims
from warehouse.oidc.models._core import (
    CheckClaimCallable,
    OIDCPublisher,
    PendingOIDCPublisher,
)

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session

ACTIVESTATE_OIDC_ISSUER_URL = "https://platform.activestate.com/api/v1/oauth/oidc"

_ACTIVESTATE_URL = "https://platform.activestate.com"


def _check_sub(
    ground_truth: str, signed_claim: str, _all_signed_claims: SignedClaims, **_kwargs
) -> bool:
    # We expect a string formatted as follows:
    #  org:<orgName>:project:<projectName>

    # Defensive: ActiveState should never give us an empty subject.
    if not signed_claim:
        raise InvalidPublisherError("Missing 'subject' claim")

    components = signed_claim.split(":")

    if len(components) < 4:
        raise InvalidPublisherError("Invalid 'subject' claim. Wrong format")

    matches = (
        f"{components[0]}:{components[1]}:{components[2]}:{components[3]}"
        == ground_truth
    )
    if not matches:
        raise InvalidPublisherError("Invalid 'subject' claim")

    return True


class ActiveStatePublisherMixin:
    """
    Common functionality for both pending and concrete ActiveState OIDC publishers.
    """

    organization: Mapped[str] = mapped_column(String, nullable=False)
    activestate_project_name: Mapped[str] = mapped_column(String, nullable=False)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    # 'actor' (The ActiveState platform username) is obtained from the user
    # while configuring the publisher We'll make an api call to ActiveState to
    # get the 'actor_id'
    actor_id: Mapped[str] = mapped_column(String, nullable=False)

    __required_verifiable_claims__: dict[str, CheckClaimCallable[Any]] = {
        "sub": _check_sub,
        "organization": oidccore.check_claim_binary(str.__eq__),
        "project": oidccore.check_claim_binary(str.__eq__),
        "actor_id": oidccore.check_claim_binary(str.__eq__),
        # This is the name of the builder in the ActiveState Platform that
        # publishes things to PyPI.
        "builder": oidccore.check_claim_invariant("pypi-publisher"),
    }

    __unchecked_claims__ = {
        "actor",
        "artifact_id",
        "ingredient",
        "organization_id",
        "project_id",
        "project_path",
        "project_visibility",
    }

    @property
    def sub(self) -> str:
        return f"org:{self.organization}:project:{self.activestate_project_name}"

    @property
    def builder(self) -> str:
        return "pypi-publisher"

    @property
    def publisher_name(self) -> str:
        return "ActiveState"

    @property
    def project(self) -> str:
        return self.activestate_project_name

    @property
    def publisher_base_url(self) -> str:
        return urllib.parse.urljoin(
            _ACTIVESTATE_URL, f"{self.organization}/{self.activestate_project_name}"
        )

    def publisher_url(self, claims: SignedClaims | None = None) -> str:
        return self.publisher_base_url

    def stored_claims(self, claims: SignedClaims | None = None) -> dict:
        return {}

    def __str__(self) -> str:
        return self.publisher_url()

    def exists(self, session: Session) -> bool:
        return session.query(
            exists().where(
                and_(
                    self.__class__.organization == self.organization,
                    self.__class__.activestate_project_name
                    == self.activestate_project_name,
                    self.__class__.actor_id == self.actor_id,
                )
            )
        ).scalar()

    @property
    def admin_details(self) -> list[tuple[str, str]]:
        """Returns ActiveState publisher configuration details for admin display."""
        return [
            ("Organization", self.organization),
            ("Project", self.activestate_project_name),
            ("Actor", self.actor),
            ("Actor ID", self.actor_id),
        ]

    @classmethod
    def lookup_by_claims(cls, session: Session, signed_claims: SignedClaims) -> Self:
        query: Query = Query(cls).filter_by(
            organization=signed_claims["organization"],
            activestate_project_name=signed_claims["project"],
            actor_id=signed_claims["actor_id"],
        )
        if publisher := query.with_session(session).one_or_none():
            return publisher
        raise InvalidPublisherError("Publisher with matching claims was not found")


class ActiveStatePublisher(ActiveStatePublisherMixin, OIDCPublisher):
    __tablename__ = "activestate_oidc_publishers"
    __mapper_args__ = {"polymorphic_identity": "activestate_oidc_publishers"}
    __table_args__ = (
        UniqueConstraint(
            "organization",
            "activestate_project_name",
            # This field is NOT populated from the form but from an API call to
            # ActiveState. We make the API call to confirm that the `actor`
            # provided actually exists.
            "actor_id",
            name="_activestate_oidc_publisher_uc",
        ),
    )

    id: Mapped[UUID] = mapped_column(ForeignKey(OIDCPublisher.id), primary_key=True)


class PendingActiveStatePublisher(ActiveStatePublisherMixin, PendingOIDCPublisher):
    __tablename__ = "pending_activestate_oidc_publishers"
    __mapper_args__ = {"polymorphic_identity": "pending_activestate_oidc_publishers"}
    __table_args__ = (  # type: ignore[assignment]
        UniqueConstraint(
            "organization",
            "activestate_project_name",
            "actor_id",
            name="_pending_activestate_oidc_publisher_uc",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        ForeignKey(PendingOIDCPublisher.id), primary_key=True
    )

    def reify(self, session: Session) -> ActiveStatePublisher:
        """
        Returns a `ActiveStatePublisher` for this `PendingActiveStatePublisher`,
        deleting the `PendingActiveStatePublisher` in the process.
        """
        # Check if the publisher already exists.  Return it if it does.
        maybe_publisher = (
            session.query(ActiveStatePublisher)
            .filter(
                ActiveStatePublisher.organization == self.organization,
                ActiveStatePublisher.activestate_project_name
                == self.activestate_project_name,
                ActiveStatePublisher.actor_id == self.actor_id,
                ActiveStatePublisher.actor == self.actor,
            )
            .one_or_none()
        )

        publisher = maybe_publisher or ActiveStatePublisher(
            organization=self.organization,
            activestate_project_name=self.activestate_project_name,
            actor_id=self.actor_id,
            actor=self.actor,
        )

        session.delete(self)
        return publisher
