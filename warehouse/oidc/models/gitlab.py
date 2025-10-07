# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
import typing

from typing import Any, Self
from uuid import UUID

from more_itertools import first_true
from pypi_attestations import GitLabPublisher as GitLabIdentity, Publisher
from sqlalchemy import ForeignKey, String, UniqueConstraint, and_, exists
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, Query, mapped_column

from warehouse.oidc.errors import InvalidPublisherError
from warehouse.oidc.interfaces import SignedClaims
from warehouse.oidc.models._core import (
    CheckClaimCallable,
    OIDCPublisher,
    PendingOIDCPublisher,
    check_existing_jti,
)
from warehouse.oidc.urls import verify_url_from_reference

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session

GITLAB_OIDC_ISSUER_URL = "https://gitlab.com"

# This expression matches the workflow filepath component of a GitLab
# `ci_config_ref_uri` OIDC claim. This requires a nontrivial (and nonregular)
# pattern, since the workflow path can contain interior slashes while also
# being delimited by slashes, and has overlapping delimiters with the
# other components of the claim.
_WORKFLOW_FILEPATH_RE = re.compile(
    r"""
    (?<=\/\/)         # lookbehind match for `//`, which terminates the repo
                      # component of the claim.

    (                 # our capture group
        .*            # match zero or more of any character, including slashes
        [^/]          # match exactly one non-slash character, to prevent
                      # empty basenames (e.g. `foo/.yml`)
        \.(yml|yaml)  # match the literal suffix `.yml` or `.yaml`
    )
    (?=@)             # lookahead match for `@`, constraining the group above
    """,
    re.X,
)


def _extract_workflow_filepath(ci_config_ref_uri: str) -> str | None:
    if match := _WORKFLOW_FILEPATH_RE.search(ci_config_ref_uri):
        return match.group(0)
    else:
        return None


def _check_project_path(
    ground_truth: str,
    signed_claim: str | None,
    _all_signed_claims: SignedClaims,
    **_kwargs,
) -> bool:

    # Defensive: GitLab should never give us an empty project_path claim.
    if not signed_claim:
        return False

    # GitLab project paths are case-insensitive.
    return signed_claim.lower() == ground_truth.lower()


def _check_ci_config_ref_uri(
    ground_truth: str,
    signed_claim: str | None,
    all_signed_claims: SignedClaims,
    **_kwargs,
) -> bool:
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


def _check_environment(
    ground_truth: str,
    signed_claim: str | None,
    _all_signed_claims: SignedClaims,
    **_kwargs,
) -> bool:
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


def _check_sub(
    ground_truth: str,
    signed_claim: str | None,
    _all_signed_claims: SignedClaims,
    **_kwargs,
) -> bool:
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

    namespace: Mapped[str] = mapped_column(String, nullable=False)
    project: Mapped[str] = mapped_column(String, nullable=False)
    workflow_filepath: Mapped[str] = mapped_column(String, nullable=False)
    environment: Mapped[str] = mapped_column(String, nullable=False)
    issuer_url: Mapped[str] = mapped_column(comment="Full URL of the issuer")

    __required_verifiable_claims__: dict[str, CheckClaimCallable[Any]] = {
        "sub": _check_sub,
        "project_path": _check_project_path,
        "ci_config_ref_uri": _check_ci_config_ref_uri,
        "jti": check_existing_jti,
    }

    __required_unverifiable_claims__: set[str] = {"ref_path", "sha"}

    __optional_verifiable_claims__: dict[str, CheckClaimCallable[Any]] = {
        "environment": _check_environment,
    }

    __unchecked_claims__ = {
        # We are not currently verifying project_id or namespace_id to protect against
        # resurrection attacks: https://github.com/pypi/warehouse/issues/15643
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
        "user_access_level",
        "groups_direct",
        "job_namespace_id",
        "job_namespace_path",
        "job_project_id",
        "job_project_path",
    }

    # Get the most specific publisher from a list of publishers,
    # where publishers constrained with an environment are more
    # specific than publishers not constrained on environment.
    @classmethod
    def _get_publisher_for_environment(
        cls, publishers: list[Self], environment: str | None
    ) -> Self | None:
        if environment:
            if specific_publisher := first_true(
                publishers, pred=lambda p: p.environment == environment
            ):
                return specific_publisher

        if general_publisher := first_true(
            publishers, pred=lambda p: p.environment == ""
        ):
            return general_publisher

        return None

    @classmethod
    def lookup_by_claims(cls, session: Session, signed_claims: SignedClaims) -> Self:
        project_path = signed_claims["project_path"]
        ci_config_ref_uri = signed_claims["ci_config_ref_uri"]
        namespace, project = project_path.rsplit("/", 1)
        environment = signed_claims.get("environment")

        if not (workflow_filepath := _extract_workflow_filepath(ci_config_ref_uri)):
            raise InvalidPublisherError(
                "Could not extract workflow filename from OIDC claims"
            )

        query: Query = Query(cls).filter_by(
            namespace=namespace,
            project=project,
            workflow_filepath=workflow_filepath,
        )
        publishers = query.with_session(session).all()
        if publisher := cls._get_publisher_for_environment(publishers, environment):
            return publisher

        raise InvalidPublisherError("Publisher with matching claims was not found")

    @property
    def project_path(self) -> str:
        return f"{self.namespace}/{self.project}"

    @property
    def sub(self) -> str:
        return f"project_path:{self.project_path}"

    @property
    def ci_config_ref_uri(self) -> str:
        return f"gitlab.com/{self.project_path}//{self.workflow_filepath}"

    @property
    def publisher_name(self) -> str:
        return "GitLab"

    @property
    def publisher_base_url(self) -> str:
        return f"https://gitlab.com/{self.project_path}"

    @property
    def jti(self) -> str:
        """Placeholder value for JTI."""
        return "placeholder"

    def publisher_url(self, claims: SignedClaims | None = None) -> str | None:
        base = self.publisher_base_url
        return f"{base}/commit/{claims['sha']}" if claims else base

    @property
    def attestation_identity(self) -> Publisher | None:
        return GitLabIdentity(
            repository=self.project_path,
            workflow_filepath=self.workflow_filepath,
            environment=self.environment if self.environment else None,
        )

    def stored_claims(self, claims: SignedClaims | None = None) -> dict:
        claims_obj = claims if claims else {}
        return {"ref_path": claims_obj.get("ref_path"), "sha": claims_obj.get("sha")}

    def __str__(self) -> str:
        return self.workflow_filepath

    def exists(self, session: Session) -> bool:
        return session.query(
            exists().where(
                and_(
                    self.__class__.namespace == self.namespace,
                    self.__class__.project == self.project,
                    self.__class__.workflow_filepath == self.workflow_filepath,
                    self.__class__.environment == self.environment,
                )
            )
        ).scalar()

    @property
    def admin_details(self) -> list[tuple[str, str]]:
        """Returns GitLab publisher configuration details for admin display."""
        details = [
            ("Project", self.project_path),
            ("Workflow", self.workflow_filepath),
        ]
        if self.environment:
            details.append(("Environment", self.environment))
        return details


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

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey(OIDCPublisher.id), primary_key=True
    )

    def verify_url(self, url: str) -> bool:
        """
        Verify a given URL against this GitLab's publisher information

        In addition to the generic Trusted Publisher verification logic in
        the parent class, the GitLab Trusted Publisher ignores the suffix `.git`
        in repo URLs, since `gitlab.com/org/repo.git` always redirects to
        `gitlab.com/org/repo`. This does not apply to subpaths like
        `gitlab.com/org/repo.git/issues`, which do not redirect to the correct URL.

        GitLab uses case-insensitive owner/repo slugs - so we perform a case-insensitive
        comparison.

        In addition to the generic Trusted Publisher verification logic in
        the parent class, the GitLab Trusted Publisher allows URLs hosted
        on `gitlab.io` for the configured repository, i.e:
        `https://${OWNER}.gitlab.io/${SUBGROUP}/${PROJECT}`.

        This method does not support the verification when the Unique Domain setting is
        used.

        The rules implemented in this method are derived from
        https://docs.gitlab.com/ee/user/project/pages/getting_started_part_one.html#project-website-examples
        https://docs.gitlab.com/ee/user/project/pages/getting_started_part_one.html#user-and-group-website-examples

        The table stems from GitLab documentation and is replicated here for clarity.
        | Namespace                    | GitLab Page URL                          |
        | ---------------------------- | ---------------------------------------- |
        | username/username.example.io | https://username.gitlab.io               |
        | acmecorp/acmecorp.example.io | https://acmecorp.gitlab.io               |
        | username/my-website          | https://username.gitlab.io/my-website    |
        | group/webshop                | https://group.gitlab.io/webshop          |
        | group/subgroup/project       | https://group.gitlab.io/subgroup/project |
        """
        lowercase_base_url = self.publisher_base_url.lower()
        if url.lower().startswith(lowercase_base_url):
            url = lowercase_base_url + url[len(lowercase_base_url) :]

        url_for_generic_check = url.removesuffix("/").removesuffix(".git")
        if verify_url_from_reference(
            reference_url=lowercase_base_url, url=url_for_generic_check
        ):
            return True

        try:
            owner, subgroup = self.namespace.split("/", maxsplit=1)
            subgroup += "/"
        except ValueError:
            owner, subgroup = self.namespace, ""

        if self.project == f"{owner}.gitlab.io" and not subgroup:
            docs_url = f"https://{owner}.gitlab.io"
        else:
            docs_url = f"https://{owner}.gitlab.io/{subgroup}{self.project}"

        return verify_url_from_reference(reference_url=docs_url, url=url)


class PendingGitLabPublisher(GitLabPublisherMixin, PendingOIDCPublisher):
    __tablename__ = "pending_gitlab_oidc_publishers"
    __mapper_args__ = {"polymorphic_identity": "pending_gitlab_oidc_publishers"}
    __table_args__ = (  # type: ignore[assignment]
        UniqueConstraint(
            "namespace",
            "project",
            "workflow_filepath",
            "environment",
            name="_pending_gitlab_oidc_publisher_uc",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey(PendingOIDCPublisher.id), primary_key=True
    )

    def reify(self, session: Session) -> GitLabPublisher:
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
