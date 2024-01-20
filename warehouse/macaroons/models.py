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

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint, orm, sql
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from warehouse import db
from warehouse.accounts.models import User
from warehouse.utils.db.types import bool_false, datetime_now


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
    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        index=True,
    )

    oidc_publisher_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("oidc_publishers.id"),
        index=True,
    )

    # Store some information about the Macaroon to give users some mechanism
    # to differentiate between them.
    description: Mapped[str]
    created: Mapped[datetime_now]
    last_used: Mapped[datetime | None]

    # Human-readable "permissions" for this macaroon, corresponding to the
    # body of the permissions ("V1") caveat.
    permissions_caveat: Mapped[dict] = mapped_column(
        JSONB, server_default=sql.text("'{}'")
    )

    # Additional state associated with this macaroon.
    # For OIDC publisher-issued macaroons, this will contain a subset of OIDC claims.
    additional: Mapped[dict | None] = mapped_column(JSONB)

    # It might be better to move this default into the database, that way we
    # make it less likely that something does it incorrectly (since the
    # default would be to generate a random key). However, it appears the
    # PostgreSQL pgcrypto extension uses OpenSSL RAND_bytes if available
    # instead of urandom. This is less than optimal, and we would generally
    # prefer to just always use urandom. Thus we'll do this ourselves here
    # in our application.
    key: Mapped[bytes] = mapped_column(default=_generate_key)

    # Intentionally not using a back references here, since we express
    # relationships in terms of the "other" side of the relationship.
    user: Mapped["User"] = orm.relationship(lazy=True, viewonly=True)
    # TODO: Can't annotate this as "OIDCPublisher" because that would create a
    #  circular import.
    oidc_publisher = orm.relationship("OIDCPublisher", lazy=True, viewonly=True)

    # Previous Macaroon were generated without a caveat restricting what
    # permissions they were valid for, so we'll store a flag to indicate whether
    # this Macaroon predated the permission caveat.
    predates_permission_caveat: Mapped[bool_false]
