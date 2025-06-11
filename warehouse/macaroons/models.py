# SPDX-License-Identifier: Apache-2.0

import os

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint, orm, sql
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from warehouse import db
from warehouse.accounts.models import User
from warehouse.macaroons.caveats import (
    Caveat,
    deserialize_obj as caveats_deserialize,
    serialize_obj as caveats_serialize,
)
from warehouse.utils.db.types import datetime_now


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

    # FIXME: Deprecated in favor of `Macaroon.caveats()`.
    # Human-readable "permissions" for this macaroon, corresponding to the
    # body of the permissions ("V1") caveat.
    permissions_caveat: Mapped[dict] = mapped_column(
        JSONB, server_default=sql.text("'{}'")
    )

    # The caveats that were attached to this Macaroon when we generated it.
    _caveats: Mapped[list] = mapped_column(
        "caveats",
        JSONB,
        server_default=sql.text("'{}'"),
        comment=(
            "The list of caveats that were attached to this Macaroon when we "
            "generated it. Users can add additional caveats at any time without "
            "communicating those additional caveats to us, which would not be "
            "reflected in this data, and thus this field must only be used for "
            "informational purposes and must not be used during the authorization "
            "or authentication process. Older Macaroons may be missing caveats as "
            "previously only the legacy permissions caveat were stored."
        ),
    )

    @property
    def caveats(self) -> list[Caveat]:
        return [caveats_deserialize(c) for c in self._caveats]

    @caveats.setter
    def caveats(self, caveats: list[Caveat]):
        self._caveats = [list(caveats_serialize(c)) for c in caveats]

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
