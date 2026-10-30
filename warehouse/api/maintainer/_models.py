# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import enum

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String, orm
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from warehouse import db
from warehouse.utils.db.types import datetime_now

if TYPE_CHECKING:
    from warehouse.accounts.models import User


class ApiKeyScope(enum.StrEnum):
    """
    What a Maintainer API key may do, as ``<domain>:<resource>:<action>``.
    A request needs both the scope on the key and the matching permission on
    the target resource.
    """

    ProjectReleasesYank = "project:releases:yank"


class ApiKey(db.Model):
    """
    A Maintainer API key. Only the SHA-256 of the full key is stored; the key
    itself is shown to the user once, at creation.
    """

    __tablename__ = "api_keys"
    __table_args__ = (
        # Keys live at most 365 days. The extra day absorbs the gap between
        # the transaction-start ``created`` and an ``expires`` computed from
        # the application clock, so a key requested with the full 365 days
        # still passes.
        CheckConstraint(
            "expires <= created + interval '366 days'",
            name="api_keys_max_lifetime",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    user: Mapped[User] = orm.relationship(foreign_keys=[user_id], lazy="joined")

    # Who minted the key. Same as user_id until organization keys arrive.
    created_by_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    name: Mapped[str]
    hashed_key: Mapped[str] = mapped_column(String(64), unique=True)
    last_four: Mapped[str] = mapped_column(String(4))
    scopes: Mapped[list[str]] = mapped_column(ARRAY(String))

    created: Mapped[datetime_now]
    expires: Mapped[datetime]
    revoked: Mapped[datetime | None]
    last_used: Mapped[datetime | None]

    # Set as each expiry reminder goes out.
    expiry_notified: Mapped[datetime | None]
    final_notice_sent: Mapped[datetime | None]
