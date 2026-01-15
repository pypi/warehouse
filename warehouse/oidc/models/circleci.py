# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import typing

from typing import Any, Self
from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint, and_, exists
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
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

CIRCLECI_OIDC_ISSUER_URL = "https://oidc.circleci.com"


class CircleCIPublisherMixin:
    """
    Common functionality for both pending and concrete CircleCI OIDC publishers.
    """

    # CircleCI identifies projects by organization ID and project ID.
    # Named with circleci_ prefix to avoid collision with
    # PendingOIDCPublisher.organization_id.
    circleci_org_id: Mapped[str] = mapped_column(String, nullable=False)
    circleci_project_id: Mapped[str] = mapped_column(String, nullable=False)
    pipeline_definition_id: Mapped[str] = mapped_column(String, nullable=False)

    __required_verifiable_claims__: dict[str, CheckClaimCallable[Any]] = {
        "oidc.circleci.com/org-id": oidccore.check_claim_binary(str.__eq__),
        "oidc.circleci.com/project-id": oidccore.check_claim_binary(str.__eq__),
        "oidc.circleci.com/pipeline-definition-id": oidccore.check_claim_binary(
            str.__eq__
        ),
        # Reject tokens from SSH re-run jobs (human access to build environment)
        "oidc.circleci.com/ssh-rerun": oidccore.check_claim_invariant(False),
    }

    __unchecked_claims__: set[str] = {
        "oidc.circleci.com/context-ids",
        "oidc.circleci.com/job-id",
        "oidc.circleci.com/pipeline-id",
        "oidc.circleci.com/vcs-ref",
        "oidc.circleci.com/vcs-origin",
        "oidc.circleci.com/workflow-id",
    }

    @property
    def publisher_name(self) -> str:
        return "CircleCI"

    @property
    def publisher_base_url(self) -> str | None:
        # CircleCI doesn't have a predictable public URL pattern for projects
        # based on org-id/project-id (they're UUIDs)
        return None

    def publisher_url(self, claims: SignedClaims | None = None) -> str | None:
        return self.publisher_base_url

    def stored_claims(self, claims: SignedClaims | None = None) -> dict:
        return {}

    def __str__(self) -> str:
        return (
            f"CircleCI project {self.circleci_project_id} "
            f"in organization {self.circleci_org_id}"
        )

    def exists(self, session: Session) -> bool:
        cls = self.__class__
        return session.query(
            exists().where(
                and_(
                    cls.circleci_org_id == self.circleci_org_id,
                    cls.circleci_project_id == self.circleci_project_id,
                    cls.pipeline_definition_id == self.pipeline_definition_id,
                )
            )
        ).scalar()

    @property
    def admin_details(self) -> list[tuple[str, str]]:
        """Returns CircleCI publisher configuration details for admin display."""
        return [
            ("Organization ID", self.circleci_org_id),
            ("Project ID", self.circleci_project_id),
            ("Pipeline Definition ID", self.pipeline_definition_id),
        ]

    @property
    def ssh_rerun(self) -> bool:
        return False

    def __getattr__(self, name: str) -> Any:
        # Map dotted claim names to actual model attributes for claim verification.
        # CircleCI uses namespaced claims like "oidc.circleci.com/org-id" which
        # can't be Python attribute names, so we map them here.
        claim_to_attr = {
            "oidc.circleci.com/org-id": "circleci_org_id",
            "oidc.circleci.com/project-id": "circleci_project_id",
            "oidc.circleci.com/pipeline-definition-id": "pipeline_definition_id",
            "oidc.circleci.com/ssh-rerun": "ssh_rerun",
        }
        if name in claim_to_attr:
            return object.__getattribute__(self, claim_to_attr[name])
        raise AttributeError(name)

    @classmethod
    def lookup_by_claims(cls, session: Session, signed_claims: SignedClaims) -> Self:
        query: Query = Query(cls).filter_by(
            circleci_org_id=signed_claims["oidc.circleci.com/org-id"],
            circleci_project_id=signed_claims["oidc.circleci.com/project-id"],
            pipeline_definition_id=signed_claims[
                "oidc.circleci.com/pipeline-definition-id"
            ],
        )
        if publisher := query.with_session(session).one_or_none():
            return publisher
        raise InvalidPublisherError("Publisher with matching claims was not found")


class CircleCIPublisher(CircleCIPublisherMixin, OIDCPublisher):
    __tablename__ = "circleci_oidc_publishers"
    __mapper_args__ = {"polymorphic_identity": "circleci_oidc_publishers"}
    __table_args__ = (
        UniqueConstraint(
            "circleci_org_id",
            "circleci_project_id",
            "pipeline_definition_id",
            name="_circleci_oidc_publisher_uc",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey(OIDCPublisher.id), primary_key=True
    )


class PendingCircleCIPublisher(CircleCIPublisherMixin, PendingOIDCPublisher):
    __tablename__ = "pending_circleci_oidc_publishers"
    __mapper_args__ = {"polymorphic_identity": "pending_circleci_oidc_publishers"}
    __table_args__ = (  # type: ignore[assignment]
        UniqueConstraint(
            "circleci_org_id",
            "circleci_project_id",
            "pipeline_definition_id",
            name="_pending_circleci_oidc_publisher_uc",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey(PendingOIDCPublisher.id), primary_key=True
    )

    def reify(self, session: Session) -> CircleCIPublisher:
        """
        Returns a `CircleCIPublisher` for this `PendingCircleCIPublisher`,
        deleting the `PendingCircleCIPublisher` in the process.
        """
        maybe_publisher = (
            session.query(CircleCIPublisher)
            .filter(
                CircleCIPublisher.circleci_org_id == self.circleci_org_id,
                CircleCIPublisher.circleci_project_id == self.circleci_project_id,
                CircleCIPublisher.pipeline_definition_id == self.pipeline_definition_id,
            )
            .one_or_none()
        )

        publisher = maybe_publisher or CircleCIPublisher(
            circleci_org_id=self.circleci_org_id,
            circleci_project_id=self.circleci_project_id,
            pipeline_definition_id=self.pipeline_definition_id,
        )

        session.delete(self)
        return publisher
