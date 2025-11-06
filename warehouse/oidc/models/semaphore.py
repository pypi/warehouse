# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import typing

from typing import Any, Self
from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint, and_, exists
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, Query, mapped_column

from warehouse.oidc.errors import InvalidPublisherError
from warehouse.oidc.interfaces import SignedClaims
from warehouse.oidc.models._core import (
    CheckClaimCallable,
    OIDCPublisher,
    PendingOIDCPublisher,
    check_claim_binary,
    check_existing_jti,
)

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session


SEMAPHORE_OIDC_ISSUER_URL_SUFFIX = ".semaphoreci.com"


def _check_sub(
    ground_truth: str,
    signed_claim: str,
    _all_signed_claims: SignedClaims,
    **_kwargs,
) -> bool:
    # Semaphore's sub claim contains:
    # org:<org-name>:project:<project-uuid>:repo:<owner/repo>:ref_type:<type>:ref:<ref>
    # We verify that it contains the expected repo

    if not signed_claim:
        return False

    # Extract the repo portion from the sub claim
    if ":repo:" not in signed_claim:
        return False

    parts = signed_claim.split(":repo:")
    if len(parts) < 2:  # pragma: no cover
        # This should be unreachable since we already checked ":repo:" is in the string
        return False

    # The repo value is between :repo: and the next :
    repo_and_rest = parts[1]
    repo_parts = repo_and_rest.split(":", 1)
    repo_in_sub = repo_parts[0]

    if not repo_in_sub:
        return False

    # Compare case-insensitively
    return repo_in_sub.lower() == ground_truth.lower()


class SemaphorePublisherMixin:
    """
    Common functionality for both pending and concrete SemaphoreCI OIDC publishers.
    """

    organization: Mapped[str] = mapped_column(String, nullable=False)
    project: Mapped[str] = mapped_column(String, nullable=False)

    __required_verifiable_claims__: dict[str, CheckClaimCallable[Any]] = {
        "sub": _check_sub,
        "repo_slug": check_claim_binary(str.__eq__),
        "jti": check_existing_jti,
    }

    __unchecked_claims__ = {
        "org",
        "org_id",
        "prj",
        "prj_id",
        "wf_id",
        "ppl_id",
        "job_id",
        "branch",
        "pr_branch",
        "pr",
        "ref",
        "ref_type",
        "tag",
        "repo",
        "job_type",
        "trg",
        "sub127",
    }

    @classmethod
    def lookup_by_claims(cls, session: Session, signed_claims: SignedClaims) -> Self:
        repo_slug = signed_claims.get("repo_slug")
        if not repo_slug:
            raise InvalidPublisherError("Missing 'repo_slug' claim")

        # repo_slug format: owner/repository
        if "/" not in repo_slug:
            raise InvalidPublisherError(
                f"Invalid 'repo_slug' claim format: {repo_slug!r}, "
                "expected 'owner/repository'"
            )

        organization, project = repo_slug.split("/", 1)

        query: Query = Query(cls).filter_by(
            organization=organization,
            project=project,
        )
        publisher = query.with_session(session).one_or_none()

        if publisher is None:
            raise InvalidPublisherError("Publisher with matching claims was not found")

        return publisher

    @property
    def publisher_name(self) -> str:
        return "SemaphoreCI"

    @property
    def repository(self) -> str:
        return f"{self.organization}/{self.project}"

    @property
    def sub(self) -> str:
        return f"repo:{self.repository}"

    @property
    def repo_slug(self) -> str:
        return self.repository

    @property
    def jti(self) -> str:
        return "placeholder"

    @property
    def publisher_base_url(self) -> str | None:
        # Semaphore projects can be hosted on any git provider
        # We return None since we don't have a canonical URL
        return None

    def publisher_url(self, claims: SignedClaims | None = None) -> str | None:
        # We don't have enough information to construct a canonical URL
        # since Semaphore can work with any git provider
        return None

    @property
    def attestation_identity(self) -> None:
        return None

    def stored_claims(self, claims: SignedClaims | None = None) -> dict:
        claims_obj = claims if claims else {}
        return {
            "ref": claims_obj.get("ref"),
            "ref_type": claims_obj.get("ref_type"),
        }

    def __str__(self) -> str:
        return self.repository

    def exists(self, session: Session) -> bool:
        return session.query(
            exists().where(
                and_(
                    self.__class__.organization == self.organization,
                    self.__class__.project == self.project,
                )
            )
        ).scalar()

    @property
    def admin_details(self) -> list[tuple[str, str]]:
        return [
            ("Organization", self.organization),
            ("Project", self.project),
        ]


class SemaphorePublisher(SemaphorePublisherMixin, OIDCPublisher):
    __tablename__ = "semaphore_oidc_publishers"
    __mapper_args__ = {"polymorphic_identity": "semaphore_oidc_publishers"}
    __table_args__ = (
        UniqueConstraint(
            "organization",
            "project",
            name="_semaphore_oidc_publisher_uc",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey(OIDCPublisher.id), primary_key=True
    )


class PendingSemaphorePublisher(SemaphorePublisherMixin, PendingOIDCPublisher):
    __tablename__ = "pending_semaphore_oidc_publishers"
    __mapper_args__ = {"polymorphic_identity": "pending_semaphore_oidc_publishers"}
    __table_args__ = (  # type: ignore[assignment]
        UniqueConstraint(
            "organization",
            "project",
            name="_pending_semaphore_oidc_publisher_uc",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey(PendingOIDCPublisher.id), primary_key=True
    )

    def reify(self, session: Session) -> SemaphorePublisher:
        """
        Returns a `SemaphorePublisher` for this `PendingSemaphorePublisher`,
        deleting the `PendingSemaphorePublisher` in the process.
        """

        maybe_publisher = (
            session.query(SemaphorePublisher)
            .filter(
                SemaphorePublisher.organization == self.organization,
                SemaphorePublisher.project == self.project,
            )
            .one_or_none()
        )

        publisher = maybe_publisher or SemaphorePublisher(
            organization=self.organization,
            project=self.project,
        )

        session.delete(self)
        return publisher
