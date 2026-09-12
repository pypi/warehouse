# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import typing

from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint, and_, exists
from sqlalchemy.orm import Mapped, mapped_column

from warehouse.oidc.interfaces import SignedClaims
from warehouse.oidc.models._core import OIDCPublisher, PendingOIDCPublisher

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session


BUILDKITE_OIDC_ISSUER_URL = "https://agent.buildkite.com"


class BuildkitePublisherMixin:
    """Common functionality for pending and concrete Buildkite publishers."""

    organization_slug: Mapped[str] = mapped_column(String, nullable=False)
    pipeline_slug: Mapped[str] = mapped_column(String, nullable=False)
    buildkite_organization_id: Mapped[str] = mapped_column(String, nullable=False)
    pipeline_id: Mapped[str] = mapped_column(String, nullable=False)
    build_branch: Mapped[str] = mapped_column(String, nullable=False)
    build_tag: Mapped[str] = mapped_column(String, nullable=False)
    step_key: Mapped[str] = mapped_column(String, nullable=False)

    @property
    def publisher_name(self) -> str:
        return "Buildkite"

    @property
    def publisher_base_url(self) -> str:
        return f"https://buildkite.com/{self.organization_slug}/{self.pipeline_slug}"

    def publisher_url(self, claims: SignedClaims | None = None) -> str:
        base = self.publisher_base_url
        if claims and (build_number := claims.get("build_number")):
            url = f"{base}/builds/{build_number}"
            if job_id := claims.get("job_id"):
                return f"{url}#{job_id}"
            return url
        return base

    def stored_claims(self, claims: SignedClaims | None = None) -> dict:
        claims_obj = claims or SignedClaims({})
        return {
            "build_number": claims_obj.get("build_number"),
            "build_branch": claims_obj.get("build_branch"),
            "build_tag": claims_obj.get("build_tag"),
            "build_commit": claims_obj.get("build_commit"),
            "step_key": claims_obj.get("step_key"),
            "job_id": claims_obj.get("job_id"),
        }

    def __str__(self) -> str:
        return f"{self.organization_slug}/{self.pipeline_slug}"

    def exists(self, session: Session) -> bool:
        return session.query(
            exists().where(
                and_(
                    self.__class__.organization_slug == self.organization_slug,
                    self.__class__.pipeline_slug == self.pipeline_slug,
                    self.__class__.build_branch == self.build_branch,
                    self.__class__.build_tag == self.build_tag,
                    self.__class__.step_key == self.step_key,
                )
            )
        ).scalar()

    @property
    def admin_details(self) -> list[tuple[str, str]]:
        details = [
            ("Organization", self.organization_slug),
            ("Pipeline", self.pipeline_slug),
        ]
        if self.buildkite_organization_id:
            details.append(("Organization ID", self.buildkite_organization_id))
        if self.pipeline_id:
            details.append(("Pipeline ID", self.pipeline_id))
        if self.build_branch:
            details.append(("Build branch", self.build_branch))
        if self.build_tag:
            details.append(("Build tag", self.build_tag))
        if self.step_key:
            details.append(("Step key", self.step_key))
        return details


class BuildkitePublisher(BuildkitePublisherMixin, OIDCPublisher):
    __tablename__ = "buildkite_oidc_publishers"
    __mapper_args__ = {"polymorphic_identity": "buildkite_oidc_publishers"}
    __table_args__ = (
        UniqueConstraint(
            "organization_slug",
            "pipeline_slug",
            "build_branch",
            "build_tag",
            "step_key",
            name="_buildkite_oidc_publisher_uc",
        ),
    )

    id: Mapped[UUID] = mapped_column(ForeignKey(OIDCPublisher.id), primary_key=True)


class PendingBuildkitePublisher(BuildkitePublisherMixin, PendingOIDCPublisher):
    __tablename__ = "pending_buildkite_oidc_publishers"
    __mapper_args__ = {"polymorphic_identity": "pending_buildkite_oidc_publishers"}
    __table_args__ = (  # type: ignore[assignment]
        UniqueConstraint(
            "organization_slug",
            "pipeline_slug",
            "build_branch",
            "build_tag",
            "step_key",
            name="_pending_buildkite_oidc_publisher_uc",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        ForeignKey(PendingOIDCPublisher.id), primary_key=True
    )

    def reify(self, session: Session) -> BuildkitePublisher:
        maybe_publisher = (
            session.query(BuildkitePublisher)
            .filter(
                BuildkitePublisher.organization_slug == self.organization_slug,
                BuildkitePublisher.pipeline_slug == self.pipeline_slug,
                BuildkitePublisher.build_branch == self.build_branch,
                BuildkitePublisher.build_tag == self.build_tag,
                BuildkitePublisher.step_key == self.step_key,
            )
            .one_or_none()
        )

        publisher = maybe_publisher or BuildkitePublisher(
            organization_slug=self.organization_slug,
            pipeline_slug=self.pipeline_slug,
            buildkite_organization_id=self.buildkite_organization_id,
            pipeline_id=self.pipeline_id,
            build_branch=self.build_branch,
            build_tag=self.build_tag,
            step_key=self.step_key,
        )
        session.delete(self)
        return publisher
