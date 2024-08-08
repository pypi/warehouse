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


import urllib

from typing import Any

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Query, mapped_column

import warehouse.oidc.models._core as oidccore

from warehouse.oidc.errors import InvalidPublisherError
from warehouse.oidc.interfaces import SignedClaims
from warehouse.oidc.models._core import (
    CheckClaimCallable,
    OIDCPublisher,
    PendingOIDCPublisher,
)

_ACTIVESTATE_URL = "https://platform.activestate.com"


def _check_sub(
    ground_truth: str, signed_claim: str, _all_signed_claims: SignedClaims
) -> bool:
    # We expect a string formatted as follows:
    #  org:<orgName>:project:<projectName>

    # Defensive: ActiveState should never give us an empty subject.
    if not signed_claim:
        raise InvalidPublisherError("Missing 'subject' claim")

    components = signed_claim.split(":")

    if len(components) < 4:
        raise InvalidPublisherError("Invalid 'subject' claim. Wrong format")

    matches = (
        f"{components[0]}:{components[1]}:{components[2]}:{components[3]}"
        == ground_truth
    )
    if not matches:
        raise InvalidPublisherError("Invalid 'subject' claim")

    return True


class ActiveStatePublisherMixin:
    """
    Common functionality for both pending and concrete ActiveState OIDC publishers.
    """

    organization = mapped_column(String, nullable=False)
    activestate_project_name = mapped_column(String, nullable=False)
    actor = mapped_column(String, nullable=False)
    # 'actor' (The ActiveState platform username) is obtained from the user
    # while configuring the publisher We'll make an api call to ActiveState to
    # get the 'actor_id'
    actor_id = mapped_column(String, nullable=False)

    __required_verifiable_claims__: dict[str, CheckClaimCallable[Any]] = {
        "sub": _check_sub,
        "organization": oidccore.check_claim_binary(str.__eq__),
        "project": oidccore.check_claim_binary(str.__eq__),
        "actor_id": oidccore.check_claim_binary(str.__eq__),
        # This is the name of the builder in the ActiveState Platform that
        # publishes things to PyPI.
        "builder": oidccore.check_claim_invariant("pypi-publisher"),
    }

    __unchecked_claims__ = {
        "actor",
        "artifact_id",
        "ingredient",
        "organization_id",
        "project_id",
        "project_path",
        "project_visibility",
    }

    @staticmethod
    def __lookup_all__(klass, signed_claims: SignedClaims):
        return Query(klass).filter_by(
            organization=signed_claims["organization"],
            activestate_project_name=signed_claims["project"],
            actor_id=signed_claims["actor_id"],
        )

    __lookup_strategies__ = [
        __lookup_all__,
    ]

    @property
    def sub(self) -> str:
        return f"org:{self.organization}:project:{self.activestate_project_name}"

    @property
    def builder(self) -> str:
        return "pypi-publisher"

    @property
    def publisher_name(self) -> str:
        return "ActiveState"

    @property
    def project(self) -> str:
        return self.activestate_project_name

    @property
    def publisher_base_url(self) -> str:
        return urllib.parse.urljoin(
            _ACTIVESTATE_URL, f"{self.organization}/{self.activestate_project_name}"
        )

    def publisher_url(self, claims: SignedClaims | None = None) -> str:
        return self.publisher_base_url

    def stored_claims(self, claims=None):
        return {}

    def __str__(self) -> str:
        return self.publisher_url()


class ActiveStatePublisher(ActiveStatePublisherMixin, OIDCPublisher):
    __tablename__ = "activestate_oidc_publishers"
    __mapper_args__ = {"polymorphic_identity": "activestate_oidc_publishers"}
    __table_args__ = (
        UniqueConstraint(
            "organization",
            "activestate_project_name",
            # This field is NOT populated from the form but from an API call to
            # ActiveState. We make the API call to confirm that the `actor`
            # provided actually exists.
            "actor_id",
            name="_activestate_oidc_publisher_uc",
        ),
    )

    id = mapped_column(
        UUID(as_uuid=True), ForeignKey(OIDCPublisher.id), primary_key=True
    )


class PendingActiveStatePublisher(ActiveStatePublisherMixin, PendingOIDCPublisher):
    __tablename__ = "pending_activestate_oidc_publishers"
    __mapper_args__ = {"polymorphic_identity": "pending_activestate_oidc_publishers"}
    __table_args__ = (
        UniqueConstraint(
            "organization",
            "activestate_project_name",
            "actor_id",
            name="_pending_activestate_oidc_publisher_uc",
        ),
    )

    id = mapped_column(
        UUID(as_uuid=True), ForeignKey(PendingOIDCPublisher.id), primary_key=True
    )

    def reify(self, session):
        """
        Returns a `ActiveStatePublisher` for this `PendingActiveStatePublisher`,
        deleting the `PendingActiveStatePublisher` in the process.
        """
        # Check if the publisher already exists.  Return it if it does.
        maybe_publisher = (
            session.query(ActiveStatePublisher)
            .filter(
                ActiveStatePublisher.organization == self.organization,
                ActiveStatePublisher.activestate_project_name
                == self.activestate_project_name,
                ActiveStatePublisher.actor_id == self.actor_id,
                ActiveStatePublisher.actor == self.actor,
            )
            .one_or_none()
        )

        publisher = maybe_publisher or ActiveStatePublisher(
            organization=self.organization,
            activestate_project_name=self.activestate_project_name,
            actor_id=self.actor_id,
            actor=self.actor,
        )

        session.delete(self)
        return publisher
