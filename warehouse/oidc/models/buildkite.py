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

from typing import Any

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Query, mapped_column
from sqlalchemy.sql.expression import func, literal

from warehouse.oidc.errors import InvalidPublisherError
from warehouse.oidc.interfaces import SignedClaims
from warehouse.oidc.models._core import (
    CheckClaimCallable,
    OIDCPublisher,
    PendingOIDCPublisher,
    check_claim_binary,
)


def _check_sub(ground_truth, signed_claim, _all_signed_claims):
    # We expect a string formatted as follows:
    #  organization:ORG:pipeline:PIPELINE:[...]
    # where [...] is a concatenation of other job context metadata. We
    # currently lack the ground context to verify that additional metadata, so
    # we limit our verification to just the ORG and PIPELINE components.

    # Defensive: Buildkite should never give us an empty subject.
    if not signed_claim:
        return False

    return signed_claim.startswith(f"{ground_truth}:")

class BuildkitePublisherMixin:
    """
    Common functionality for both pending and concrete Buildkite OIDC publishers.
    """

    organization_slug = mapped_column(String, nullable=False)
    pipeline_slug = mapped_column(String, nullable=False)
    build_branch = mapped_column(String, nullable=False)
    build_tag = mapped_column(String, nullable=False)
    step_key = mapped_column(String, nullable=False)

    __required_verifiable_claims__: dict[str, CheckClaimCallable[Any]] = {
        "sub": _check_sub,
        "organization_slug": check_claim_binary(str.__eq__),
        "pipeline_slug": check_claim_binary(str.__eq__),
    }

    __required_unverifiable_claims__: set[str] = {
        "build_number",
        "job_id",
        "agent_id",
    }

    __optional_verifiable_claims__: dict[str, CheckClaimCallable[Any]] = {
        "build_branch": check_claim_binary(str.__eq__),
        "build_tag": check_claim_binary(str.__eq__),
        "step_key": check_claim_binary(str.__eq__),
    }

    __unchecked_claims__ = {
        "organization_id",
        "pipeline_id",
        "build_commit",
    }

    @staticmethod
    def __lookup_all__(klass, signed_claims: SignedClaims) -> Query | None:
        return (
            Query(klass)
            .filter_by(
                organization_slug=signed_claims["organization_slug"],
                pipeline_slug=signed_claims["pipeline_slug"],
            )
        )

    __lookup_strategies__ = [
        __lookup_all__,
    ]

    @property
    def publisher_name(self):
        return "Buildkite"

    @property
    def sub(self):
        return f"organization:{self.organization_slug}:pipeline:{self.pipeline_slug}"

    def publisher_url(self, claims=None):
        base = f"https://buildkite.com/{self.organization_slug}/{self.pipeline_slug}"

        build_number = claims.get("build_number") if claims else None
        job_id = claims.get("job_id") if claims else None

        if build_number and job_id:
            return f"{base}/builds/{build_number}#{job_id}"
        elif build_number:
            return f"{base}/builds/{build_number}"
        return base

    def __str__(self):
        return f"{self.organization_slug}/{self.pipeline_slug}"


class BuildkitePublisher(BuildkitePublisherMixin, OIDCPublisher):
    __tablename__ = "buildkite_oidc_publishers"
    __mapper_args__ = {"polymorphic_identity": "buildkite_oidc_publishers"}
    __table_args__ = (
        UniqueConstraint(
            "organization_slug",
            "pipeline_slug",
            name="_buildkite_oidc_publisher_uc",
        ),
    )

    id = mapped_column(
        UUID(as_uuid=True), ForeignKey(OIDCPublisher.id), primary_key=True
    )


class PendingBuildkitePublisher(BuildkitePublisherMixin, PendingOIDCPublisher):
    __tablename__ = "pending_buildkite_oidc_publishers"
    __mapper_args__ = {"polymorphic_identity": "pending_buildkite_oidc_publishers"}
    __table_args__ = (
        UniqueConstraint(
            "organization_slug",
            "pipeline_slug",
            name="_pending_buildkite_oidc_publisher_uc",
        ),
    )

    id = mapped_column(
        UUID(as_uuid=True), ForeignKey(PendingOIDCPublisher.id), primary_key=True
    )

    def reify(self, session):
        """
        Returns a `BuildkitePublisher` for this `PendingBuildkitePublisher`,
        deleting the `PendingBuildkitePublisher` in the process.
        """

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
            build_branch=self.build_branch,
            build_tag=self.build_tag,
            step_key=self.step_key,
        )

        session.delete(self)
        return publisher
