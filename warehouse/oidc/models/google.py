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


from sqlalchemy import Column, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from warehouse.oidc.models._core import (
    OIDCPublisher,
    PendingOIDCPublisher,
    _check_claim_binary,
    _check_claim_invariant,
)


def _check_sub(ground_truth, signed_claim, all_signed_claims):
    # If we haven't set a subject for the publisher, we don't need to check
    # this claim.
    if ground_truth is None:
        return True

    # Defensive: Google should never send us an empty or null subject, but
    # we check regardless.
    if not signed_claim:
        return False

    return ground_truth == signed_claim


class GooglePublisherMixin:
    """
    Common functionality for both pending and concrete Google OIDC
    providers.
    """

    email = Column(String, nullable=False)
    sub = Column(String, nullable=True)

    __required_verifiable_claims__ = {
        "email": _check_claim_binary(str.__eq__),
        "email_verified": _check_claim_invariant(True),
    }

    __optional_verifiable_claims__ = {"sub": _check_sub}

    __unchecked_claims__ = {"azp", "google"}

    @property
    def email_verified(self):
        # We don't consider a claim set valid unless `email_verified` is true;
        # no other states are possible.
        return True

    def __str__(self):
        return self.email


class GooglePublisher(GooglePublisherMixin, OIDCPublisher):
    __tablename__ = "google_oidc_publishers"
    __mapper_args__ = {"polymorphic_identity": "google_oidc_publishers"}
    __table_args__ = (
        UniqueConstraint(
            "email",
            "sub",
            name="_google_oidc_publisher_uc",
        ),
    )

    id = Column(UUID(as_uuid=True), ForeignKey(OIDCPublisher.id), primary_key=True)


class PendingGooglePublisher(GooglePublisherMixin, PendingOIDCPublisher):
    __tablename__ = "pending_google_oidc_publishers"
    __mapper_args__ = {"polymorphic_identity": "pending_google_oidc_publishers"}
    __table_args__ = (
        UniqueConstraint(
            "email",
            "sub",
            name="_pending_google_oidc_publisher_uc",
        ),
    )

    id = Column(
        UUID(as_uuid=True), ForeignKey(PendingOIDCPublisher.id), primary_key=True
    )

    def reify(self, session):
        """
        Returns a `GooglePublisher` for this `PendingGooglePublisher`,
        deleting the `PendingGooglePublisher` in the process.
        """

        maybe_publisher = (
            session.query(GooglePublisher)
            .filter(
                GooglePublisher.email == self.email,
                GooglePublisher.sub == self.sub,
            )
            .one_or_none()
        )

        publisher = maybe_publisher or GooglePublisher(
            email=self.email,
            sub=self.sub,
        )

        session.delete(self)
        return publisher
