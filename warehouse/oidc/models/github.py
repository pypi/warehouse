# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
import typing

from typing import Any, Self
from uuid import UUID

from more_itertools import first_true
from pypi_attestations import GitHubPublisher as GitHubIdentity, Publisher
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
from warehouse.oidc.urls import verify_url_from_reference

if typing.TYPE_CHECKING:
    from sqlalchemy.orm import Session

GITHUB_OIDC_ISSUER_URL = "https://token.actions.githubusercontent.com"

# This expression matches the workflow filename component of a GitHub
# "workflow ref", i.e. the value present in the `workflow_ref` and
# `job_workflow_ref` claims. This requires a nontrivial (and nonregular)
# pattern, since the workflow filename and other components of the workflow
# can contain overlapping delimiters (such as `@` in the workflow filename,
# or `git` refs that look like workflow filenames).
_WORKFLOW_FILENAME_RE = re.compile(
    r"""
    (                   # our capture group
        [^/]+           # match one or more non-slash characters
        \.(yml|yaml)    # match the literal suffix `.yml` or `.yaml`
    )
    (?=@)               # lookahead match for `@`, constraining the group above
    """,
    re.X,
)


def _extract_workflow_filename(workflow_ref: str) -> str | None:
    if match := _WORKFLOW_FILENAME_RE.search(workflow_ref):
        return match.group(0)
    else:
        return None


def _check_repository(
    ground_truth: str, signed_claim: str, _all_signed_claims: SignedClaims, **_kwargs
) -> bool:
    # Defensive: GitHub should never give us an empty repository claim.
    if not signed_claim:
        return False

    # GitHub repository names are case-insensitive.
    return signed_claim.lower() == ground_truth.lower()


def _check_job_workflow_ref(
    ground_truth: str, signed_claim: str, all_signed_claims: SignedClaims, **_kwargs
) -> bool:
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


def _check_environment(
    ground_truth: str,
    signed_claim: str | None,
    _all_signed_claims: SignedClaims,
    **_kwargs,
) -> bool:
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


def _check_sub(
    ground_truth: str, signed_claim: str, _all_signed_claims: SignedClaims, **_kwargs
) -> bool:
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


def _check_event_name(
    ground_truth: str, signed_claim: str, _all_signed_claims: SignedClaims, **_kwargs,
) -> bool:
    if signed_claim == "pull_request_target":
        raise InvalidPublisherError(
            "Publishing from a workflow invoked via 'pull_request_target' is "
            "not supported."
        )
    else:
        return True


class GitHubPublisherMixin:
    """
    Common functionality for both pending and concrete GitHub OIDC publishers.
    """

    repository_name: Mapped[str] = mapped_column(String, nullable=False)
    repository_owner: Mapped[str] = mapped_column(String, nullable=False)
    repository_owner_id: Mapped[str] = mapped_column(String, nullable=False)
    workflow_filename: Mapped[str] = mapped_column(String, nullable=False)
    environment: Mapped[str] = mapped_column(String, nullable=False)

    __required_verifiable_claims__: dict[str, CheckClaimCallable[Any]] = {
        "sub": _check_sub,
        "repository": _check_repository,
        "repository_owner": check_claim_binary(str.__eq__),
        "repository_owner_id": check_claim_binary(str.__eq__),
        "job_workflow_ref": _check_job_workflow_ref,
        "jti": check_existing_jti,
        "event_name": _check_event_name,
    }

    __required_unverifiable_claims__: set[str] = {"ref", "sha"}

    __optional_verifiable_claims__: dict[str, CheckClaimCallable[Any]] = {
        "environment": _check_environment,
    }

    __unchecked_claims__ = {
        "actor",
        "actor_id",
        "run_id",
        "run_number",
        "run_attempt",
        "head_ref",
        "base_ref",
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

    # Get the most specific publisher from a list of publishers,
    # where publishers constrained with an environment are more
    # specific than publishers not constrained on environment.
    @classmethod
    def _get_publisher_for_environment(
        cls, publishers: list[Self], environment: str | None
    ) -> Self | None:
        if environment:
            if specific_publisher := first_true(
                publishers, pred=lambda p: p.environment == environment.lower()
            ):
                return specific_publisher

        if general_publisher := first_true(
            publishers, pred=lambda p: p.environment == ""
        ):
            return general_publisher

        return None

    @classmethod
    def lookup_by_claims(cls, session: Session, signed_claims: SignedClaims) -> Self:
        repository = signed_claims["repository"]
        repository_owner, repository_name = repository.split("/", 1)
        job_workflow_ref = signed_claims["job_workflow_ref"]
        environment = signed_claims.get("environment")

        if not (job_workflow_filename := _extract_workflow_filename(job_workflow_ref)):
            raise InvalidPublisherError(
                "Could not job extract workflow filename from OIDC claims"
            )

        query: Query = Query(cls).filter_by(
            repository_name=repository_name,
            repository_owner=repository_owner,
            repository_owner_id=signed_claims["repository_owner_id"],
            workflow_filename=job_workflow_filename,
        )
        publishers = query.with_session(session).all()

        if publisher := cls._get_publisher_for_environment(publishers, environment):
            return publisher
        else:
            raise InvalidPublisherError("Publisher with matching claims was not found")

    @property
    def _workflow_slug(self) -> str:
        return f".github/workflows/{self.workflow_filename}"

    @property
    def publisher_name(self) -> str:
        return "GitHub"

    @property
    def repository(self) -> str:
        return f"{self.repository_owner}/{self.repository_name}"

    @property
    def job_workflow_ref(self) -> str:
        return f"{self.repository}/{self._workflow_slug}"

    @property
    def sub(self) -> str:
        return f"repo:{self.repository}"

    @property
    def publisher_base_url(self) -> str:
        return f"https://github.com/{self.repository}"

    @property
    def jti(self) -> str:
        """Placeholder value for JTI."""
        return "placeholder"

    @property
    def event_name(self) -> str:
        """Placeholder value for event_name (not used)"""
        return "placeholder"

    def publisher_url(self, claims: SignedClaims | None = None) -> str:
        base = self.publisher_base_url
        sha = claims.get("sha") if claims else None

        if sha:
            return f"{base}/commit/{sha}"
        return base

    @property
    def attestation_identity(self) -> Publisher | None:
        return GitHubIdentity(
            repository=self.repository,
            workflow=self.workflow_filename,
            environment=self.environment if self.environment else None,
        )

    def stored_claims(self, claims: SignedClaims | None = None) -> dict:
        claims_obj = claims if claims else {}
        return {"ref": claims_obj.get("ref"), "sha": claims_obj.get("sha")}

    def __str__(self) -> str:
        return self.workflow_filename

    def exists(self, session: Session) -> bool:
        return session.query(
            exists().where(
                and_(
                    self.__class__.repository_name == self.repository_name,
                    self.__class__.repository_owner == self.repository_owner,
                    self.__class__.workflow_filename == self.workflow_filename,
                    self.__class__.environment == self.environment,
                )
            )
        ).scalar()

    @property
    def admin_details(self) -> list[tuple[str, str]]:
        """Returns GitHub publisher configuration details for admin display."""
        details = [
            ("Repository", self.repository),
            ("Workflow", self.workflow_filename),
            ("Owner ID", self.repository_owner_id),
        ]
        if self.environment:
            details.append(("Environment", self.environment))
        return details


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

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey(OIDCPublisher.id), primary_key=True
    )

    def verify_url(self, url: str) -> bool:
        """
        Verify a given URL against this GitHub's publisher information

        In addition to the generic Trusted Publisher verification logic in
        the parent class, the GitHub Trusted Publisher allows URLs hosted
        on `github.io` for the configured repository, i.e:
        `https://${OWNER}.github.io/${REPO_NAME}/`.

        As with the generic verification, we allow subpaths of the `.io` URL,
        but we normalize using `rfc3986` to reject things like
        `https://${OWNER}.github.io/${REPO_NAME}/../malicious`, which would
        resolve to a URL outside the `/$REPO_NAME` path.

        The suffix `.git` in repo URLs is ignored, since `github.com/org/repo.git`
        always redirects to `github.com/org/repo`. This does not apply to subpaths,
        like `github.com/org/repo.git/issues`, which do not redirect to the correct URL.

        GitHub uses case-insensitive owner/repo slugs - so we perform a case-insensitive
        comparison.
        """
        docs_url = (
            f"https://{self.repository_owner}.github.io/{self.repository_name}".lower()
        )
        normalized_url_prefixes = (self.publisher_base_url.lower(), docs_url)
        for prefix in normalized_url_prefixes:
            if url.lower().startswith(prefix):
                url = prefix + url[len(prefix) :]
                break

        url_for_generic_check = url.removesuffix("/").removesuffix(".git")
        if verify_url_from_reference(
            reference_url=self.publisher_base_url.lower(),
            url=url_for_generic_check,
        ):
            return True

        return verify_url_from_reference(reference_url=docs_url, url=url)


class PendingGitHubPublisher(GitHubPublisherMixin, PendingOIDCPublisher):
    __tablename__ = "pending_github_oidc_publishers"
    __mapper_args__ = {"polymorphic_identity": "pending_github_oidc_publishers"}
    __table_args__ = (  # type: ignore[assignment]
        UniqueConstraint(
            "repository_name",
            "repository_owner",
            "workflow_filename",
            "environment",
            name="_pending_github_oidc_publisher_uc",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey(PendingOIDCPublisher.id), primary_key=True
    )

    def reify(self, session: Session) -> GitHubPublisher:
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
