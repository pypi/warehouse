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


def _check_repository(ground_truth, signed_claim, all_signed_claims):
    # Defensive: GitHub should never give us an empty repository claim.
    if not signed_claim:
        return False

    # GitHub repository names are case-insensitive.
    return signed_claim.lower() == ground_truth.lower()


def _check_job_workflow_ref(ground_truth, signed_claim, all_signed_claims):
    # We expect a string formatted as follows:
    #   OWNER/REPO/.github/workflows/WORKFLOW.yml@REF
    # where REF is the value of either the `ref` or `sha` claims.

    # Defensive: GitHub should never give us an empty job_workflow_ref,
    # but we check for one anyways just in case.
    if not signed_claim:
        raise InvalidPublisherError("The job_workflow_ref claim is empty")

    # We need at least one of these to be non-empty
    # In most cases, the `ref` claim will be present (e.g: "refs/heads/main")
    # and used in `job_workflow_ref`. However, there are certain cases
    # (such as creating a GitHub deployment tied to a specific commit SHA), where
    # a workflow triggered by that deployment will have an empty `ref` claim, and
    # the `job_workflow_ref` claim will use the `sha` claim instead.
    ref = all_signed_claims.get("ref")
    sha = all_signed_claims.get("sha")
    if not (ref or sha):
        raise InvalidPublisherError("The ref and sha claims are empty")

    expected = {f"{ground_truth}@{_ref}" for _ref in [ref, sha] if _ref}
    if signed_claim not in expected:
        raise InvalidPublisherError(
            "The job_workflow_ref claim does not match, expecting one of "
            f"{sorted(expected)!r}, got {signed_claim!r}"
        )

    return True


def _check_environment(ground_truth, signed_claim, all_signed_claims):
    # When there is an environment, we expect a case-insensitive string.
    # https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment
    # For tokens that are generated outside of an environment, the claim will
    # be missing.

    # If we haven't set an environment name for the publisher, we don't need to
    # check this claim
    if ground_truth == "":
        return True

    # Defensive: GitHub might give us an empty environment if this token wasn't
    # generated from within an environment, in which case the check should
    # fail.
    if not signed_claim:
        return False

    # We store the normalized environment name, but we normalize both here to
    # ensure we can't accidentally become case-sensitive.
    return ground_truth.lower() == signed_claim.lower()


def _check_sub(ground_truth, signed_claim, _all_signed_claims):
    # We expect a string formatted as follows:
    #  repo:ORG/REPO[:OPTIONAL-STUFF]
    # where :OPTIONAL-STUFF is a concatenation of other job context
    # metadata. We currently lack the ground context to verify that
    # additional metadata, so we limit our verification to just the ORG/REPO
    # component.

    # Defensive: GitHub should never give us an empty subject.
    if not signed_claim:
        return False

    components = signed_claim.split(":")
    if len(components) < 2:
        return False

    org, repo, *_ = components
    if not org or not repo:
        return False

    # The sub claim is case-insensitive
    return f"{org}:{repo}".lower() == ground_truth.lower()


class GitHubPublisherMixin:
    """
    Common functionality for both pending and concrete GitHub OIDC publishers.
    """

    repository_name = mapped_column(String, nullable=False)
    repository_owner = mapped_column(String, nullable=False)
    repository_owner_id = mapped_column(String, nullable=False)
    workflow_filename = mapped_column(String, nullable=False)
    environment = mapped_column(String, nullable=False)

    __required_verifiable_claims__: dict[str, CheckClaimCallable[Any]] = {
        "sub": _check_sub,
        "repository": _check_repository,
        "repository_owner": check_claim_binary(str.__eq__),
        "repository_owner_id": check_claim_binary(str.__eq__),
        "job_workflow_ref": _check_job_workflow_ref,
    }

    __required_unverifiable_claims__: set[str] = {"ref", "sha"}

    __optional_verifiable_claims__: dict[str, CheckClaimCallable[Any]] = {
        "environment": _check_environment,
    }

    __unchecked_claims__ = {
        "actor",
        "actor_id",
        "jti",
        "run_id",
        "run_number",
        "run_attempt",
        "head_ref",
        "base_ref",
        "event_name",
        "ref_type",
        "repository_id",
        "workflow",
        "repository_visibility",
        "workflow_sha",
        "job_workflow_sha",
        "workflow_ref",
        "runner_environment",
        "environment_node_id",
        "enterprise",
        "enterprise_id",
        "ref_protected",
    }

    @staticmethod
    def __lookup_all__(klass, signed_claims: SignedClaims) -> Query | None:
        # This lookup requires the environment claim to be present;
        # if it isn't, bail out early.
        if not (environment := signed_claims.get("environment")):
            return None

        repository = signed_claims["repository"]
        repository_owner, repository_name = repository.split("/", 1)
        workflow_prefix = f"{repository}/.github/workflows/"
        workflow_ref = signed_claims["job_workflow_ref"].removeprefix(workflow_prefix)

        return (
            Query(klass)
            .filter_by(
                repository_name=repository_name,
                repository_owner=repository_owner,
                repository_owner_id=signed_claims["repository_owner_id"],
                environment=environment.lower(),
            )
            .filter(
                literal(workflow_ref).like(func.concat(klass.workflow_filename, "%"))
            )
        )

    @staticmethod
    def __lookup_no_environment__(klass, signed_claims: SignedClaims) -> Query | None:
        repository = signed_claims["repository"]
        repository_owner, repository_name = repository.split("/", 1)
        workflow_prefix = f"{repository}/.github/workflows/"
        workflow_ref = signed_claims["job_workflow_ref"].removeprefix(workflow_prefix)

        return (
            Query(klass)
            .filter_by(
                repository_name=repository_name,
                repository_owner=repository_owner,
                repository_owner_id=signed_claims["repository_owner_id"],
                environment="",
            )
            .filter(
                literal(workflow_ref).like(func.concat(klass.workflow_filename, "%"))
            )
        )

    __lookup_strategies__ = [
        __lookup_all__,
        __lookup_no_environment__,
    ]

    @property
    def _workflow_slug(self):
        return f".github/workflows/{self.workflow_filename}"

    @property
    def publisher_name(self):
        return "GitHub"

    @property
    def repository(self):
        return f"{self.repository_owner}/{self.repository_name}"

    @property
    def job_workflow_ref(self):
        return f"{self.repository}/{self._workflow_slug}"

    @property
    def sub(self):
        return f"repo:{self.repository}"

    @property
    def publisher_base_url(self):
        return f"https://github.com/{self.repository}"

    def publisher_url(self, claims=None):
        base = self.publisher_base_url
        sha = claims.get("sha") if claims else None

        if sha:
            return f"{base}/commit/{sha}"
        return base

    def stored_claims(self, claims=None):
        claims = claims if claims else {}
        return {"ref": claims.get("ref"), "sha": claims.get("sha")}

    def __str__(self):
        return self.workflow_filename


class GitHubPublisher(GitHubPublisherMixin, OIDCPublisher):
    __tablename__ = "github_oidc_publishers"
    __mapper_args__ = {"polymorphic_identity": "github_oidc_publishers"}
    __table_args__ = (
        UniqueConstraint(
            "repository_name",
            "repository_owner",
            "workflow_filename",
            "environment",
            name="_github_oidc_publisher_uc",
        ),
    )

    id = mapped_column(
        UUID(as_uuid=True), ForeignKey(OIDCPublisher.id), primary_key=True
    )


class PendingGitHubPublisher(GitHubPublisherMixin, PendingOIDCPublisher):
    __tablename__ = "pending_github_oidc_publishers"
    __mapper_args__ = {"polymorphic_identity": "pending_github_oidc_publishers"}
    __table_args__ = (
        UniqueConstraint(
            "repository_name",
            "repository_owner",
            "workflow_filename",
            "environment",
            name="_pending_github_oidc_publisher_uc",
        ),
    )

    id = mapped_column(
        UUID(as_uuid=True), ForeignKey(PendingOIDCPublisher.id), primary_key=True
    )

    def reify(self, session):
        """
        Returns a `GitHubPublisher` for this `PendingGitHubPublisher`,
        deleting the `PendingGitHubPublisher` in the process.
        """

        maybe_publisher = (
            session.query(GitHubPublisher)
            .filter(
                GitHubPublisher.repository_name == self.repository_name,
                GitHubPublisher.repository_owner == self.repository_owner,
                GitHubPublisher.workflow_filename == self.workflow_filename,
                GitHubPublisher.environment == self.environment,
            )
            .one_or_none()
        )

        publisher = maybe_publisher or GitHubPublisher(
            repository_name=self.repository_name,
            repository_owner=self.repository_owner,
            repository_owner_id=self.repository_owner_id,
            workflow_filename=self.workflow_filename,
            environment=self.environment,
        )

        session.delete(self)
        return publisher
