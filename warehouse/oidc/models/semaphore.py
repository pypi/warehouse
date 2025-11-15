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
    # org:<org-name>:project:<project-uuid>:repo:<repo-name>:ref_type:<type>:ref:<ref>
    # The :repo: field contains just the repository name (not owner/repo)
    # ground_truth is in format "repo_slug:owner/repo", so we extract the repo_slug part

    # Extract the repo portion from the sub claim
    if not signed_claim or ":repo:" not in signed_claim:
        return False

    repo_in_sub = signed_claim.split(":repo:", 1)[1].split(":", 1)[0]
    if not repo_in_sub:
        return False

    # Extract repo_slug from ground_truth (format: "repo_slug:owner/repo")
    repo_slug = ground_truth.removeprefix("repo_slug:")

    # Extract just the repo name from repo_slug (owner/repo -> repo)
    repo_name = repo_slug.split("/")[-1]

    # Compare case-insensitively
    return repo_in_sub.lower() == repo_name.lower()


class SemaphorePublisherMixin:
    """
    Common functionality for both pending and concrete SemaphoreCI OIDC publishers.
    """

    organization: Mapped[str] = mapped_column(String, nullable=False)
    organization_id: Mapped[str] = mapped_column(String, nullable=False)
    project: Mapped[str] = mapped_column(String, nullable=False)
    project_id: Mapped[str] = mapped_column(String, nullable=False)
    repo_slug: Mapped[str] = mapped_column(String, nullable=False)

    __required_verifiable_claims__: dict[str, CheckClaimCallable[Any]] = {
        "sub": _check_sub,
        "org": check_claim_binary(str.__eq__),
        "org_id": check_claim_binary(str.__eq__),
        "prj": check_claim_binary(str.__eq__),
        "prj_id": check_claim_binary(str.__eq__),
        "repo_slug": check_claim_binary(str.__eq__),
        "jti": check_existing_jti,
    }

    __unchecked_claims__ = {
        "repo",
        "wf_id",
        "ppl_id",
        "job_id",
        "branch",
        "pr_branch",
        "pr",
        "ref",
        "ref_type",
        "tag",
        "job_type",
        "trg",
        "sub127",
    }

    @classmethod
    def lookup_by_claims(cls, session: Session, signed_claims: SignedClaims) -> Self:
        org = signed_claims.get("org")
        org_id = signed_claims.get("org_id")
        prj = signed_claims.get("prj")
        prj_id = signed_claims.get("prj_id")
        repo_slug = signed_claims.get("repo_slug")

        if not org or not org_id or not prj or not prj_id or not repo_slug:
            raise InvalidPublisherError(
                "Missing required claims: 'org', 'org_id', 'prj', 'prj_id', or 'repo_slug'"
            )

        query: Query = Query(cls).filter_by(
            organization=org,
            organization_id=org_id,
            project=prj,
            project_id=prj_id,
            repo_slug=repo_slug,
        )
        publisher = query.with_session(session).one_or_none()

        if publisher is None:
            raise InvalidPublisherError("Publisher with matching claims was not found")

        return publisher

    @property
    def publisher_name(self) -> str:
        return "SemaphoreCI"

    @property
    def sub(self) -> str:
        return f"repo_slug:{self.repo_slug}"

    @property
    def repo(self) -> str:
        # Extract just the repository name from owner/repo
        return (
            self.repo_slug.split("/")[-1]
            if "/" in self.repo_slug
            else self.repo_slug
        )

    @property
    def org(self) -> str:
        return self.organization

    @property
    def org_id(self) -> str:
        return self.organization_id

    @property
    def prj(self) -> str:
        return self.project

    @property
    def prj_id(self) -> str:
        return self.project_id

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
        return self.repo_slug

    def exists(self, session: Session) -> bool:
        return session.query(
            exists().where(
                and_(
                    self.__class__.organization == self.organization,
                    self.__class__.organization_id == self.organization_id,
                    self.__class__.project == self.project,
                    self.__class__.project_id == self.project_id,
                    self.__class__.repo_slug == self.repo_slug,
                )
            )
        ).scalar()

    @property
    def admin_details(self) -> list[tuple[str, str]]:
        return [
            ("Organization", self.organization),
            ("Organization ID", self.organization_id),
            ("Project", self.project),
            ("Project ID", self.project_id),
            ("Repository", self.repo_slug),
        ]


class SemaphorePublisher(SemaphorePublisherMixin, OIDCPublisher):
    __tablename__ = "semaphore_oidc_publishers"
    __mapper_args__ = {"polymorphic_identity": "semaphore_oidc_publishers"}
    __table_args__ = (
        UniqueConstraint(
            "organization",
            "organization_id",
            "project",
            "project_id",
            "repo_slug",
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
            "organization_id",
            "project",
            "project_id",
            "repo_slug",
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
                SemaphorePublisher.organization_id == self.organization_id,
                SemaphorePublisher.project == self.project,
                SemaphorePublisher.project_id == self.project_id,
                SemaphorePublisher.repo_slug == self.repo_slug,
            )
            .one_or_none()
        )

        publisher = maybe_publisher or SemaphorePublisher(
            organization=self.organization,
            organization_id=self.organization_id,
            project=self.project,
            project_id=self.project_id,
            repo_slug=self.repo_slug,
        )

        session.delete(self)
        return publisher
