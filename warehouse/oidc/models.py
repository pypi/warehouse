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

import sentry_sdk

from sqlalchemy import Column, ForeignKey, String, orm
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
        Project, secondary=OIDCProviderProjectAssociation, backref="oidc_providers"
    )

    __mapper_args__ = {"polymorphic_on": discriminator}

    # A map of claim names to "check" functions, each of which
    # has the signature `check(ground-truth, signed-claim) -> bool`.
    __verifiable_claims__ = dict()

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
    __unchecked_claims__ = set()

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
        known_claims = self.__verifiable_claims__.keys().union(
            self.__preverified_claims__, self.__unchecked_claims__
        )
        unaccounted_claims = known_claims.difference(signed_claims.keys())
        if unaccounted_claims:
            sentry_sdk.capture_message(
                f"JWT for {self.__class__.__name__} has unaccounted claims: {unaccounted_claims}"
            )

        # Finally, perform the actual claim verification.
        for claim_name, check in self.__verifiable_claims__.items():
            if not check(self.getattr(claim_name), signed_claims[claim_name]):
                return False

        return True


class GitHubProvider(OIDCProvider):
    __tablename__ = "github_oidc_providers"
    __mapper_args__ = {"polymorphic_identity": "GitHubProvider"}

    id = Column(UUID(as_uuid=True), ForeignKey(OIDCProvider.id), primary_key=True)
    repository_name = Column(String)
    owner = Column(String)
    owner_id = Column(String)
    workflow_name = Column(String)

    __verifiable_claims__ = {
        "repository": str.__eq__,
        "job_workflow_ref": str.startswith,
        "actor": str.__eq__,
        "workflow": str.__eq__,
    }

    __unchecked_claims__ = {
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
    }

    @property
    def repository(self):
        return f"{self.owner}/{self.repository_name}"

    @property
    def job_workflow_ref(self):
        return f"{self.repository}/.github/workflows/{self.workflow_name}.yml"

    @property
    def actor(self):
        return self.owner

    @property
    def workflow(self):
        return self.workflow_name
