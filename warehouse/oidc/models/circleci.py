# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import typing

from typing import Any, Self
from uuid import UUID

from more_itertools import first_true
from pypi_attestations import Publisher
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


def _check_context_id(
    ground_truth: str,
    signed_claim: list[str] | None,
    _all_signed_claims: SignedClaims,
    **_kwargs,
) -> bool:
    # The context-ids claim is an array of UUIDs for contexts used in the job.
    # If we haven't set a context_id for the publisher, we don't need to check.
    if ground_truth == "":
        return True

    # If we require a context but the token has no context-ids, fail.
    if not signed_claim:
        return False

    # Check if our required context_id is in the array of context IDs.
    return ground_truth in signed_claim


def _check_optional_string(
    ground_truth: str,
    signed_claim: str | None,
    _all_signed_claims: SignedClaims,
    **_kwargs,
) -> bool:
    # If we haven't set a value for the publisher, we don't need to check.
    if ground_truth == "":
        return True

    # If we require a value but the token doesn't have it, fail.
    if not signed_claim:
        return False

    return ground_truth == signed_claim


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
    context_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Optional VCS claims for additional security constraints
    # vcs_ref: e.g., "refs/heads/main"
    # vcs_origin: e.g., "github.com/organization-123/repo-1"
    vcs_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    vcs_origin: Mapped[str | None] = mapped_column(String, nullable=True)

    __required_verifiable_claims__: dict[str, CheckClaimCallable[Any]] = {
        "oidc.circleci.com/org-id": oidccore.check_claim_binary(str.__eq__),
        "oidc.circleci.com/project-id": oidccore.check_claim_binary(str.__eq__),
        "oidc.circleci.com/pipeline-definition-id": oidccore.check_claim_binary(
            str.__eq__
        ),
        # Reject tokens from SSH re-run jobs (human access to build environment)
        "oidc.circleci.com/ssh-rerun": oidccore.check_claim_invariant(False),
    }

    __optional_verifiable_claims__: dict[str, CheckClaimCallable[Any]] = {
        "oidc.circleci.com/context-ids": _check_context_id,
        "oidc.circleci.com/vcs-ref": _check_optional_string,
        "oidc.circleci.com/vcs-origin": _check_optional_string,
    }

    __unchecked_claims__: set[str] = {
        "oidc.circleci.com/job-id",
        "oidc.circleci.com/pipeline-id",
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

    @property
    def attestation_identity(self) -> Publisher | None:
        # CircleCI attestation support pending pypi-attestations library support.
        # Fulcio supports CircleCI OIDC tokens, but pypi-attestations needs to add
        # a CircleCIPublisher identity class before we can enable attestations.
        # See: https://github.com/pypi/pypi-attestations
        return None

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
                    cls.context_id == self.context_id,
                    cls.vcs_ref == self.vcs_ref,
                    cls.vcs_origin == self.vcs_origin,
                )
            )
        ).scalar()

    @property
    def admin_details(self) -> list[tuple[str, str]]:
        """Returns CircleCI publisher configuration details for admin display."""
        details = [
            ("Organization ID", self.circleci_org_id),
            ("Project ID", self.circleci_project_id),
            ("Pipeline Definition ID", self.pipeline_definition_id),
        ]
        if self.context_id:
            details.append(("Context ID", self.context_id))
        if self.vcs_ref:
            details.append(("VCS Ref", self.vcs_ref))
        if self.vcs_origin:
            details.append(("VCS Origin", self.vcs_origin))
        return details

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
            "oidc.circleci.com/context-ids": "context_id",
            "oidc.circleci.com/vcs-ref": "vcs_ref",
            "oidc.circleci.com/vcs-origin": "vcs_origin",
        }
        if name in claim_to_attr:
            return object.__getattribute__(self, claim_to_attr[name])
        raise AttributeError(name)

    @classmethod
    def _get_publisher_for_context(
        cls, publishers: list[Self], context_ids: list[str] | None
    ) -> Self | None:
        # Find the most specific publisher: one with a matching context_id takes
        # precedence over a publisher without context_id constraint.
        if context_ids:
            if specific_publisher := first_true(
                publishers, pred=lambda p: p.context_id in context_ids
            ):
                return specific_publisher

        # Fall back to a publisher without context_id constraint (empty string)
        if general_publisher := first_true(
            publishers, pred=lambda p: p.context_id == ""
        ):
            return general_publisher

        return None

    @classmethod
    def lookup_by_claims(cls, session: Session, signed_claims: SignedClaims) -> Self:
        context_ids = signed_claims.get("oidc.circleci.com/context-ids")

        query: Query = Query(cls).filter_by(
            circleci_org_id=signed_claims["oidc.circleci.com/org-id"],
            circleci_project_id=signed_claims["oidc.circleci.com/project-id"],
            pipeline_definition_id=signed_claims[
                "oidc.circleci.com/pipeline-definition-id"
            ],
        )
        publishers = query.with_session(session).all()

        if publisher := cls._get_publisher_for_context(publishers, context_ids):
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
            "context_id",
            "vcs_ref",
            "vcs_origin",
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
            "context_id",
            "vcs_ref",
            "vcs_origin",
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
                CircleCIPublisher.context_id == self.context_id,
                CircleCIPublisher.vcs_ref == self.vcs_ref,
                CircleCIPublisher.vcs_origin == self.vcs_origin,
            )
            .one_or_none()
        )

        publisher = maybe_publisher or CircleCIPublisher(
            circleci_org_id=self.circleci_org_id,
            circleci_project_id=self.circleci_project_id,
            pipeline_definition_id=self.pipeline_definition_id,
            context_id=self.context_id,
            vcs_ref=self.vcs_ref,
            vcs_origin=self.vcs_origin,
        )

        session.delete(self)
        return publisher
