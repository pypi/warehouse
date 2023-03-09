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


from collections.abc import Callable
from typing import Any

import sentry_sdk

from sqlalchemy import Column, ForeignKey, String, UniqueConstraint, orm
from sqlalchemy.dialects.postgresql import UUID

from warehouse import db
from warehouse.macaroons.models import Macaroon
from warehouse.oidc.interfaces import SignedClaims
from warehouse.packaging.models import File, Project


def _check_claim_binary(binary_func):
    """
    Wraps a binary comparison function so that it takes three arguments instead,
    ignoring the third.

    This is used solely to make claim verification compatible with "trivial"
    checks like `str.__eq__`.
    """

    def wrapper(ground_truth, signed_claim, all_signed_claims):
        return binary_func(ground_truth, signed_claim)

    return wrapper


def _check_job_workflow_ref(ground_truth, signed_claim, all_signed_claims):
    # We expect a string formatted as follows:
    #   OWNER/REPO/.github/workflows/WORKFLOW.yml@REF
    # where REF is the value of the `ref` claim.

    # Defensive: GitHub should never give us an empty job_workflow_ref,
    # but we check for one anyways just in case.
    if not signed_claim:
        return False

    ref = all_signed_claims.get("ref")
    if not ref:
        return False

    return f"{ground_truth}@{ref}" == signed_claim


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

    return f"{components[0]}:{components[1]}" == ground_truth


class OIDCPublisherProjectAssociation(db.Model):
    __tablename__ = "oidc_publisher_project_association"

    oidc_publisher_id = Column(
        UUID(as_uuid=True),
        ForeignKey("oidc_publishers.id"),
        nullable=False,
        primary_key=True,
    )
    project_id = Column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, primary_key=True
    )


class OIDCPublisherMixin:
    """
    A mixin for common functionality between all OIDC publishers, including
    "pending" publishers that don't correspond to an extant project yet.
    """

    # Each hierarchy of OIDC publishers (both `OIDCPublisher` and
    # `PendingOIDCPublisher`) use a `discriminator` column for model
    # polymorphism, but the two are not mutually polymorphic at the DB level.
    discriminator = Column(String)

    # A map of claim names to "check" functions, each of which
    # has the signature `check(ground-truth, signed-claim, all-signed-claims) -> bool`.
    __verifiable_claims__: dict[
        str, Callable[[Any, Any, dict[str, Any]], bool]
    ] = dict()

    # Claims that have already been verified during the JWT signature
    # verification phase.
    __preverified_claims__ = {
        "iss",
        "iat",
        "nbf",
        "exp",
        "aud",
    }

    # Individual publishers should explicitly override this set,
    # indicating any custom claims that are known to be present but are
    # not checked as part of verifying the JWT.
    __unchecked_claims__: set[str] = set()

    @classmethod
    def all_known_claims(cls):
        """
        Returns all claims "known" to this publisher.
        """
        return (
            cls.__verifiable_claims__.keys()
            | cls.__preverified_claims__
            | cls.__unchecked_claims__
        )

    def verify_claims(self, signed_claims: SignedClaims):
        """
        Given a JWT that has been successfully decoded (checked for a valid
        signature and basic claims), verify it against the more specific
        claims of this publisher.
        """

        # Defensive programming: treat the absence of any claims to verify
        # as a failure rather than trivially valid.
        if not self.__verifiable_claims__:
            return False

        # All claims should be accounted for.
        # The presence of an unaccounted claim is not an error, only a warning
        # that the JWT payload has changed.
        unaccounted_claims = signed_claims.keys() - self.all_known_claims()
        if unaccounted_claims:
            sentry_sdk.capture_message(
                f"JWT for {self.__class__.__name__} has unaccounted claims: "
                f"{unaccounted_claims}"
            )

        # Finally, perform the actual claim verification.
        for claim_name, check in self.__verifiable_claims__.items():
            # All verifiable claims are mandatory. The absence of a missing
            # claim *is* an error, since it indicates a breaking change in the
            # JWT's payload.
            signed_claim = signed_claims.get(claim_name)
            if signed_claim is None:
                sentry_sdk.capture_message(
                    f"JWT for {self.__class__.__name__} is missing claim: {claim_name}"
                )
                return False

            if not check(getattr(self, claim_name), signed_claim, signed_claims):
                return False

        return True

    @property
    def publisher_name(self):  # pragma: no cover
        # Only concrete subclasses are constructed.
        return NotImplemented

    @property
    def publisher_url(self):  # pragma: no cover
        # Only concrete subclasses are constructed.
        return NotImplemented


class OIDCPublisher(OIDCPublisherMixin, db.Model):
    __tablename__ = "oidc_publishers"

    projects = orm.relationship(
        Project,
        secondary=OIDCPublisherProjectAssociation.__table__,  # type: ignore
        backref="oidc_publishers",
    )
    macaroons = orm.relationship(
        Macaroon, backref="oidc_publisher", cascade="all, delete-orphan", lazy=True
    )
    files = orm.relationship(
        File,
        backref="oidc_publisher",
        lazy=True,
    )

    __mapper_args__ = {
        "polymorphic_identity": "oidc_publishers",
        "polymorphic_on": OIDCPublisherMixin.discriminator,
    }


class PendingOIDCPublisher(OIDCPublisherMixin, db.Model):
    """
    A "pending" OIDC publisher, i.e. one that's been registered by a user
    but doesn't correspond to an existing PyPI project yet.
    """

    __tablename__ = "pending_oidc_publishers"

    project_name = Column(String, nullable=False)
    added_by_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )

    __mapper_args__ = {
        "polymorphic_identity": "pending_oidc_publishers",
        "polymorphic_on": OIDCPublisherMixin.discriminator,
    }

    def reify(self, session):  # pragma: no cover
        """
        Return an equivalent "normal" OIDC publisher model for this pending publisher,
        deleting the pending publisher in the process.
        """

        # Only concrete subclasses are constructed.
        return NotImplemented


class GitHubPublisherMixin:
    """
    Common functionality for both pending and concrete GitHub OIDC publishers.
    """

    repository_name = Column(String)
    repository_owner = Column(String)
    repository_owner_id = Column(String)
    workflow_filename = Column(String)

    __verifiable_claims__ = {
        "sub": _check_sub,
        "repository": _check_claim_binary(str.__eq__),
        "repository_owner": _check_claim_binary(str.__eq__),
        "repository_owner_id": _check_claim_binary(str.__eq__),
        "job_workflow_ref": _check_job_workflow_ref,
    }

    __unchecked_claims__ = {
        "actor",
        "actor_id",
        "jti",
        "ref",
        "sha",
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
    }

    @property
    def _workflow_slug(self):
        return f".github/workflows/{self.workflow_filename}"

    @property
    def publisher_name(self):
        return "GitHub"

    @property
    def publisher_url(self):
        # NOTE: Until we embed the SHA, this URL is not guaranteed to contain
        # the exact contents of the workflow that their OIDC publisher corresponds to.
        return f"https://github.com/{self.repository}/blob/HEAD/{self._workflow_slug}"

    @property
    def repository(self):
        return f"{self.repository_owner}/{self.repository_name}"

    @property
    def job_workflow_ref(self):
        return f"{self.repository}/{self._workflow_slug}"

    @property
    def sub(self):
        return f"repo:{self.repository}"

    def __str__(self):
        return f"{self.workflow_filename} @ {self.repository}"


class GitHubPublisher(GitHubPublisherMixin, OIDCPublisher):
    __tablename__ = "github_oidc_publishers"
    __mapper_args__ = {"polymorphic_identity": "github_oidc_publishers"}
    __table_args__ = (
        UniqueConstraint(
            "repository_name",
            "repository_owner",
            "workflow_filename",
            name="_github_oidc_publisher_uc",
        ),
    )

    id = Column(UUID(as_uuid=True), ForeignKey(OIDCPublisher.id), primary_key=True)


class PendingGitHubPublisher(GitHubPublisherMixin, PendingOIDCPublisher):
    __tablename__ = "pending_github_oidc_publishers"
    __mapper_args__ = {"polymorphic_identity": "pending_github_oidc_publishers"}
    __table_args__ = (
        UniqueConstraint(
            "repository_name",
            "repository_owner",
            "workflow_filename",
            name="_pending_github_oidc_publisher_uc",
        ),
    )

    id = Column(
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
            )
            .one_or_none()
        )

        publisher = maybe_publisher or GitHubPublisher(
            repository_name=self.repository_name,
            repository_owner=self.repository_owner,
            repository_owner_id=self.repository_owner_id,
            workflow_filename=self.workflow_filename,
        )

        session.delete(self)
        return publisher
