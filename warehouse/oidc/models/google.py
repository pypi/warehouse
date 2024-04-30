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

from warehouse.oidc.interfaces import SignedClaims
from warehouse.oidc.models._core import (
    CheckClaimCallable,
    OIDCPublisher,
    PendingOIDCPublisher,
    check_claim_binary,
    check_claim_invariant,
)


def _check_sub(
    ground_truth: str, signed_claim: str, all_signed_claims: SignedClaims
) -> bool:
    # If we haven't set a subject for the publisher, we don't need to check
    # this claim.
    if ground_truth == "":
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

    email = mapped_column(String, nullable=False)
    sub = mapped_column(String, nullable=True)

    __required_verifiable_claims__: dict[str, CheckClaimCallable[Any]] = {
        "email": check_claim_binary(str.__eq__),
        "email_verified": check_claim_invariant(True),
    }

    __optional_verifiable_claims__: dict[str, CheckClaimCallable[Any]] = {
        "sub": _check_sub
    }

    __unchecked_claims__ = {"azp", "google"}

    @staticmethod
    def __lookup_all__(klass, signed_claims: SignedClaims) -> Query | None:
        return Query(klass).filter_by(
            email=signed_claims["email"], sub=signed_claims["sub"]
        )

    @staticmethod
    def __lookup_no_sub__(klass, signed_claims: SignedClaims) -> Query | None:
        return Query(klass).filter_by(email=signed_claims["email"], sub="")

    __lookup_strategies__ = [
        __lookup_all__,
        __lookup_no_sub__,
    ]

    @property
    def publisher_name(self):
        return "Google"

    @property
    def publisher_base_url(self):
        return None

    def publisher_url(self, claims=None):
        return None

    def stored_claims(self, claims=None):
        return {}

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

    id = mapped_column(
        UUID(as_uuid=True), ForeignKey(OIDCPublisher.id), primary_key=True
    )


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

    id = mapped_column(
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
