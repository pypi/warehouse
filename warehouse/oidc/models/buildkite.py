# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import typing

from typing import Any, Self
from uuid import UUID

from more_itertools import first_true
from sqlalchemy import ForeignKey, String, UniqueConstraint, and_, exists
from sqlalchemy.orm import Mapped, Query, mapped_column

from warehouse.oidc.errors import InvalidPublisherError
from warehouse.oidc.interfaces import SignedClaims
from warehouse.oidc.models._core import (
    CheckClaimCallable,
    OIDCPublisher,
    PendingOIDCPublisher,
    check_claim_binary,
)

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from warehouse.oidc.services import OIDCPublisherService


BUILDKITE_OIDC_ISSUER_URL = "https://agent.buildkite.com"

_PINNED_ID_CLAIMS = (
    ("organization_id", "buildkite_organization_id", "organization"),
    ("pipeline_id", "pipeline_id", "pipeline"),
)


def _check_optional_constraint(
    ground_truth: str,
    signed_claim: str | None,
    _all_signed_claims: SignedClaims,
    **_kwargs,
) -> bool:
    return ground_truth in ("", signed_claim)


class BuildkitePublisherMixin:
    """Common functionality for pending and concrete Buildkite publishers."""

    organization_slug: Mapped[str] = mapped_column(String, nullable=False)
    pipeline_slug: Mapped[str] = mapped_column(String, nullable=False)
    buildkite_organization_id: Mapped[str] = mapped_column(String, nullable=False)
    pipeline_id: Mapped[str] = mapped_column(String, nullable=False)
    build_branch: Mapped[str] = mapped_column(String, nullable=False)
    build_tag: Mapped[str] = mapped_column(String, nullable=False)
    step_key: Mapped[str] = mapped_column(String, nullable=False)

    __required_verifiable_claims__: dict[str, CheckClaimCallable[Any]] = {
        "organization_slug": check_claim_binary(str.__eq__),
        "pipeline_slug": check_claim_binary(str.__eq__),
    }

    __required_unverifiable_claims__: set[str] = {
        "sub",
        "build_number",
        "build_commit",
        "job_id",
        "agent_id",
        "runner_environment",
        "build_source",
    }

    __optional_verifiable_claims__: dict[str, CheckClaimCallable[Any]] = {
        "build_branch": _check_optional_constraint,
        "build_tag": _check_optional_constraint,
        "step_key": _check_optional_constraint,
    }

    __unchecked_claims__ = {
        "build_id",
        "cluster_id",
        "cluster_name",
        "queue_id",
        "queue_key",
    }
    __unchecked_prefixed_claims__ = {"agent_tag:"}

    @classmethod
    def all_known_claims(cls) -> set[str]:
        return super().all_known_claims() | {  # type: ignore[misc]
            claim for claim, _, _ in _PINNED_ID_CLAIMS
        }

    def _verify_pinned_ids(self, signed_claims: SignedClaims) -> None:
        for claim, attribute, label in _PINNED_ID_CLAIMS:
            pinned_id = getattr(self, attribute)
            signed_id = signed_claims.get(claim)
            if signed_id is not None and not isinstance(signed_id, str):
                raise InvalidPublisherError(
                    f"Buildkite token claim {claim!r} must be a string"
                )
            if not pinned_id:
                continue
            if not signed_id:
                raise InvalidPublisherError(
                    f"Buildkite publisher is pinned to a {label} ID, but the token "
                    f"is missing claim {claim!r}; request it with --claim {claim}"
                )
            if pinned_id != signed_id:
                raise InvalidPublisherError(
                    f"Buildkite token claim {claim!r} does not match the publisher's "
                    f"pinned {label} ID"
                )

    def _pinned_ids_match(self, signed_claims: SignedClaims) -> bool:
        return all(
            not getattr(self, attribute)
            or getattr(self, attribute) == signed_claims.get(claim)
            for claim, attribute, _ in _PINNED_ID_CLAIMS
        )

    @classmethod
    def lookup_by_claims(cls, session: Session, signed_claims: SignedClaims) -> Self:
        query: Query = Query(cls).filter_by(
            organization_slug=signed_claims["organization_slug"],
            pipeline_slug=signed_claims["pipeline_slug"],
        )
        publishers = query.with_for_update().with_session(session).all()

        candidates = [
            publisher
            for publisher in publishers
            if all(
                not configured or configured == signed_claims.get(claim)
                for claim, configured in (
                    ("build_branch", publisher.build_branch),
                    ("build_tag", publisher.build_tag),
                    ("step_key", publisher.step_key),
                )
            )
        ]

        if publisher := first_true(
            candidates,
            pred=lambda publisher: publisher._pinned_ids_match(signed_claims),
        ):
            return publisher
        if candidates:
            candidates[0]._verify_pinned_ids(signed_claims)
        raise InvalidPublisherError("Publisher with matching claims was not found")

    def verify_claims(
        self,
        signed_claims: SignedClaims,
        publisher_service: OIDCPublisherService,
    ) -> bool:
        self._verify_pinned_ids(signed_claims)
        return super().verify_claims(  # type: ignore[misc]
            signed_claims, publisher_service
        )

    def pin_claims(self, signed_claims: SignedClaims) -> None:
        for claim, attribute, _ in _PINNED_ID_CLAIMS:
            if not getattr(self, attribute) and (signed_id := signed_claims.get(claim)):
                setattr(self, attribute, signed_id)

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
