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
)


def _check_project_path(ground_truth, signed_claim, all_signed_claims):
    # Defensive: GitLab should never give us an empty project_path claim.
    if not signed_claim:
        return False

    # GitLab project paths are case-insensitive.
    return signed_claim.lower() == ground_truth.lower()


def _check_ci_config_ref_uri(ground_truth, signed_claim, all_signed_claims):
    # We expect a string formatted as follows:
    #   gitlab.com/OWNER/REPO//WORKFLOW_PATH/WORKFLOW_FILE.yml@REF
    # where REF is the value of the `ref_path` claim.

    # Defensive: GitLab should never give us an empty ci_config_ref_uri,
    # but we check for one anyway just in case.
    if not signed_claim:
        raise InvalidPublisherError("The ci_config_ref_uri claim is empty")

    # Same defensive check as above but for ref_path and sha.
    ref_path = all_signed_claims.get("ref_path")
    sha = all_signed_claims.get("sha")
    if not (ref_path and sha):
        raise InvalidPublisherError("The ref_path and sha claims are empty")

    expected = {f"{ground_truth}@{_ref}" for _ref in [ref_path, sha] if _ref}
    if signed_claim not in expected:
        raise InvalidPublisherError(
            "The ci_config_ref_uri claim does not match, expecting one of "
            f"{sorted(expected)!r}, got {signed_claim!r}"
        )

    return True


def _check_environment(ground_truth, signed_claim, all_signed_claims):
    # When there is an environment, we expect a string.
    # For tokens that are generated outside of an environment, the claim will
    # be missing.

    # If we haven't set an environment name for the publisher, we don't need to
    # check this claim
    if ground_truth == "":
        return True

    # Defensive: GitLab might give us an empty environment if this token wasn't
    # generated from within an environment, in which case the check should
    # fail.
    if not signed_claim:
        return False

    return ground_truth == signed_claim


def _check_sub(ground_truth, signed_claim, _all_signed_claims):
    # We expect a string formatted as follows:
    # project_path:NAMESPACE/PROJECT[:OPTIONAL-STUFF]
    # where :OPTIONAL-STUFF is a concatenation of other job context
    # metadata. We currently lack the ground context to verify that
    # additional metadata, so we limit our verification to just the
    # NAMESPACE/PROJECT component.

    # Defensive: GitLab should never give us an empty subject.
    if not signed_claim:
        return False

    components = signed_claim.split(":")
    if len(components) < 2:
        return False

    namespace, project, *_ = components
    if not namespace or not project:
        return False

    # The sub claim is case-insensitive
    return f"{namespace}:{project}".lower() == ground_truth.lower()


class GitLabPublisherMixin:
    """
    Common functionality for both pending and concrete GitLab OIDC publishers.
    """

    namespace = mapped_column(String, nullable=False)
    project = mapped_column(String, nullable=False)
    workflow_filepath = mapped_column(String, nullable=False)
    environment = mapped_column(String, nullable=False)

    __required_verifiable_claims__: dict[str, CheckClaimCallable[Any]] = {
        "sub": _check_sub,
        "project_path": _check_project_path,
        "ci_config_ref_uri": _check_ci_config_ref_uri,
    }

    __required_unverifiable_claims__: set[str] = {"ref_path", "sha"}

    __optional_verifiable_claims__: dict[str, CheckClaimCallable[Any]] = {
        "environment": _check_environment,
    }

    __unchecked_claims__ = {
        # We are not currently verifying project_id or namespace_id to protect against
        # resurrection attacks: https://github.com/pypi/warehouse/issues/13575
        "project_id",
        "namespace_id",
        "namespace_path",
        "user_id",
        "user_login",
        "user_email",
        "user_identities",
        "pipeline_id",
        "pipeline_source",
        "job_id",
        "ref",
        "ref_type",
        "ref_protected",
        "environment_protected",
        "deployment_tier",
        "environment_action",
        "runner_id",
        "runner_environment",
        "ci_config_sha",
        "project_visibility",
        "jti",
        "user_access_level",
        "groups_direct",
    }

    @staticmethod
    def __lookup_all__(klass, signed_claims: SignedClaims) -> Query | None:
        # This lookup requires the environment claim to be present;
        # if it isn't, bail out early.
        if not (environment := signed_claims.get("environment")):
            return None

        project_path = signed_claims["project_path"]
        ci_config_ref_prefix = f"gitlab.com/{project_path}//"
        ci_config_ref = signed_claims["ci_config_ref_uri"].removeprefix(
            ci_config_ref_prefix
        )
        namespace, project = project_path.rsplit("/", 1)

        return (
            Query(klass)
            .filter_by(
                namespace=namespace,
                project=project,
                environment=environment,
            )
            .filter(
                literal(ci_config_ref).like(func.concat(klass.workflow_filepath, "%"))
            )
        )

    @staticmethod
    def __lookup_no_environment__(klass, signed_claims: SignedClaims) -> Query | None:
        project_path = signed_claims["project_path"]
        ci_config_ref_prefix = f"gitlab.com/{project_path}//"
        ci_config_ref = signed_claims["ci_config_ref_uri"].removeprefix(
            ci_config_ref_prefix
        )
        namespace, project = project_path.rsplit("/", 1)

        return (
            Query(klass)
            .filter_by(
                namespace=namespace,
                project=project,
                environment="",
            )
            .filter(
                literal(ci_config_ref).like(func.concat(klass.workflow_filepath, "%"))
            )
        )

    __lookup_strategies__ = [
        __lookup_all__,
        __lookup_no_environment__,
    ]

    @property
    def project_path(self):
        return f"{self.namespace}/{self.project}"

    @property
    def sub(self):
        return f"project_path:{self.project_path}"

    @property
    def ci_config_ref_uri(self):
        return f"gitlab.com/{self.project_path}//{self.workflow_filepath}"

    @property
    def publisher_name(self):
        return "GitLab"

    @property
    def publisher_base_url(self):
        return f"https://gitlab.com/{self.project_path}"

    def publisher_url(self, claims=None):
        base = self.publisher_base_url
        return f"{base}/commit/{claims['sha']}" if claims else base

    def stored_claims(self, claims=None):
        claims = claims if claims else {}
        return {"ref_path": claims.get("ref_path"), "sha": claims.get("sha")}

    def __str__(self):
        return self.workflow_filepath


class GitLabPublisher(GitLabPublisherMixin, OIDCPublisher):
    __tablename__ = "gitlab_oidc_publishers"
    __mapper_args__ = {"polymorphic_identity": "gitlab_oidc_publishers"}
    __table_args__ = (
        UniqueConstraint(
            "namespace",
            "project",
            "workflow_filepath",
            "environment",
            name="_gitlab_oidc_publisher_uc",
        ),
    )

    id = mapped_column(
        UUID(as_uuid=True), ForeignKey(OIDCPublisher.id), primary_key=True
    )


class PendingGitLabPublisher(GitLabPublisherMixin, PendingOIDCPublisher):
    __tablename__ = "pending_gitlab_oidc_publishers"
    __mapper_args__ = {"polymorphic_identity": "pending_gitlab_oidc_publishers"}
    __table_args__ = (
        UniqueConstraint(
            "namespace",
            "project",
            "workflow_filepath",
            "environment",
            name="_pending_gitlab_oidc_publisher_uc",
        ),
    )

    id = mapped_column(
        UUID(as_uuid=True), ForeignKey(PendingOIDCPublisher.id), primary_key=True
    )

    def reify(self, session):
        """
        Returns a `GitLabPublisher` for this `PendingGitLabPublisher`,
        deleting the `PendingGitLabPublisher` in the process.
        """

        maybe_publisher = (
            session.query(GitLabPublisher)
            .filter(
                GitLabPublisher.namespace == self.namespace,
                GitLabPublisher.project == self.project,
                GitLabPublisher.workflow_filepath == self.workflow_filepath,
                GitLabPublisher.environment == self.environment,
            )
            .one_or_none()
        )

        publisher = maybe_publisher or GitLabPublisher(
            namespace=self.namespace,
            project=self.project,
            workflow_filepath=self.workflow_filepath,
            environment=self.environment,
        )

        session.delete(self)
        return publisher
