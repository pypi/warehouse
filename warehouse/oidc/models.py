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


from typing import Any, Callable, Dict, Set

import sentry_sdk

from sqlalchemy import Column, ForeignKey, String, UniqueConstraint, orm
from sqlalchemy.dialects.postgresql import UUID

from warehouse import db
from warehouse.packaging.models import Project


class OIDCProviderProjectAssociation(db.Model):
    __tablename__ = "oidc_provider_project_association"

    oidc_provider_id = Column(
        UUID(as_uuid=True),
        ForeignKey("oidc_providers.id"),
        nullable=False,
        primary_key=True,
    )
    project_id = Column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, primary_key=True
    )


class OIDCProvider(db.Model):
    __tablename__ = "oidc_providers"

    discriminator = Column(String)
    projects = orm.relationship(
        Project,
        secondary=OIDCProviderProjectAssociation.__table__,  # type: ignore
        backref="oidc_providers",
    )

    __mapper_args__ = {
        "polymorphic_identity": "oidc_providers",
        "polymorphic_on": discriminator,
    }

    # A map of claim names to "check" functions, each of which
    # has the signature `check(ground-truth, signed-claim) -> bool`.
    __verifiable_claims__: Dict[str, Callable[[Any, Any], bool]] = dict()

    # Claims that have already been verified during the JWT signature
    # verification phase.
    __preverified_claims__ = {
        "iss",
        "iat",
        "nbf",
        "exp",
        "aud",
    }

    # Individual providers should explicitly override this set,
    # indicating any custom claims that are known to be present but are
    # not checked as part of verifying the JWT.
    __unchecked_claims__: Set[str] = set()

    @classmethod
    def all_known_claims(cls):
        """
        Returns all claims "known" to this provider.
        """
        return (
            cls.__verifiable_claims__.keys()
            | cls.__preverified_claims__
            | cls.__unchecked_claims__
        )

    def verify_claims(self, signed_claims):
        """
        Given a JWT that has been successfully decoded (checked for a valid
        signature and basic claims), verify it against the more specific
        claims of this provider.
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

            if not check(getattr(self, claim_name), signed_claim):
                return False

        return True

    @property
    def provider_name(self):  # pragma: no cover
        # Only concrete subclasses of OIDCProvider are constructed.
        return NotImplemented


class GitHubProvider(OIDCProvider):
    __tablename__ = "github_oidc_providers"
    __mapper_args__ = {"polymorphic_identity": "github_oidc_providers"}
    __table_args__ = (
        UniqueConstraint(
            "repository_name",
            "owner",
            "workflow_name",
            name="_github_oidc_provider_uc",
        ),
    )

    id = Column(UUID(as_uuid=True), ForeignKey(OIDCProvider.id), primary_key=True)
    repository_name = Column(String)
    owner = Column(String)
    owner_id = Column(String)
    workflow_name = Column(String)

    __verifiable_claims__ = {
        "repository": str.__eq__,
        "workflow": str.__eq__,
    }

    __unchecked_claims__ = {
        "actor",
        "jti",
        "sub",
        "ref",
        "sha",
        "run_id",
        "run_number",
        "run_attempt",
        "head_ref",
        "base_ref",
        "event_name",
        "ref_type",
        # TODO(#11096): Support reusable workflows.
        "job_workflow_ref",
    }

    @property
    def provider_name(self):
        return "GitHub"

    @property
    def repository(self):
        return f"{self.owner}/{self.repository_name}"

    @property
    def workflow(self):
        return self.workflow_name

    def __str__(self):
        return f"{self.workflow_name} @ {self.repository}"
