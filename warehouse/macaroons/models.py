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

import os

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    UniqueConstraint,
    orm,
    sql,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from warehouse import db


def _generate_key():
    return os.urandom(32)


class Macaroon(db.Model):
    __tablename__ = "macaroons"
    __table_args__ = (
        UniqueConstraint(
            "description", "user_id", name="_user_macaroons_description_uc"
        ),
        CheckConstraint(
            "(user_id::text IS NULL) <> (oidc_publisher_id::text IS NULL)",
            name="_user_xor_oidc_publisher_macaroon",
        ),
    )

    # Macaroons come in two forms: they either belong to a user, or they
    # authenticate for one or more projects.
    # * In the user case, a Macaroon has an associated user, and *might* have
    #   additional project scope restrictions as part of its caveats.
    # * In the project case, a Macaroon does *not* have an explicit associated
    #   project. Instead, depending on how its used (its request context),
    #   it identifies one of the projects scoped in its caveats.
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )

    oidc_publisher_id = Column(
        UUID(as_uuid=True), ForeignKey("oidc_publishers.id"), nullable=True, index=True
    )

    # Store some information about the Macaroon to give users some mechanism
    # to differentiate between them.
    description = Column(String, nullable=False)
    created = Column(DateTime, nullable=False, server_default=sql.func.now())
    last_used = Column(DateTime, nullable=True)

    # Human-readable "permissions" for this macaroon, corresponding to the
    # body of the permissions ("V1") caveat.
    permissions_caveat = Column(JSONB, nullable=False, server_default=sql.text("'{}'"))

    # Additional state associated with this macaroon.
    # For OIDC publisher-issued macaroons, this will contain a subset of OIDC claims.
    additional = Column(JSONB, nullable=True)

    # It might be better to move this default into the database, that way we
    # make it less likely that something does it incorrectly (since the
    # default would be to generate a random key). However, it appears the
    # PostgreSQL pgcrypto extension uses OpenSSL RAND_bytes if available
    # instead of urandom. This is less than optimal, and we would generally
    # prefer to just always use urandom. Thus we'll do this ourselves here
    # in our application.
    key = Column(LargeBinary, nullable=False, default=_generate_key)

    # Intentionally not using a back references here, since we express
    # relationships in terms of the "other" side of the relationship.
    user = orm.relationship("User", lazy=True, viewonly=True)
    oidc_publisher = orm.relationship("OIDCPublisher", lazy=True, viewonly=True)
