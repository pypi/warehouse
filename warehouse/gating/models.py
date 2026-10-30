# SPDX-License-Identifier: Apache-2.0

"""
Models for the release gating mechanism.

A *gate* is a named, revocable hold on a `Release`. While any gate on a release
blocks, the release is withheld from the Simple index and the JSON API, and its
files are not copied into the CDN-backed cache bucket.

A `kind` is the name of an `IGatePolicy` registered by some other package. This
one defines no gates.
"""

from __future__ import annotations

import datetime
import enum
import typing

from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint, orm
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from warehouse import db
from warehouse.utils.attrs import make_repr
from warehouse.utils.db.types import datetime_now

if typing.TYPE_CHECKING:
    from warehouse.packaging.models import Release


class GateStatus(enum.StrEnum):
    """
    The state of an individual hold. Only `Pending` and `Failed` block;
    `Bypassed` is an administrator override and `Expired` is a policy that did
    not decide within its timeout.

    Gates are not deleted when they resolve, so a release keeps a record of
    what held it.
    """

    Pending = "pending"
    Passed = "passed"
    Failed = "failed"
    Bypassed = "bypassed"
    Expired = "expired"


# Anything not listed here lets a release through, so a new `GateStatus` member
# is non-blocking by default.
BLOCKING_GATE_STATUSES: frozenset[GateStatus] = frozenset(
    {GateStatus.Pending, GateStatus.Failed}
)

# Mirrored by the `sa.String(64)` in the migration, which cannot import this.
GATE_KIND_MAX_LENGTH = 64


class ReleaseGate(db.Model):
    __tablename__ = "release_gates"
    __table_args__ = (
        # One gate per (release, kind). Another file uploaded into a release
        # that already has this gate resets the existing row rather than
        # stacking a second one.
        UniqueConstraint("release_id", "kind", name="_release_gate_kind_uc"),
        Index("release_gates_status_idx", "status"),
        # The timeout sweep only looks at pending gates, ordered by age.
        Index("release_gates_pending_created_idx", "created"),
    )
    __repr__ = make_repr("kind", "status")

    release_id: Mapped[UUID] = mapped_column(
        ForeignKey("releases.id", onupdate="CASCADE", ondelete="CASCADE"),
        index=True,
    )
    release: Mapped[Release] = orm.relationship(back_populates="gates")

    # Not a database enum: gates are registered in code, so adding one must not
    # need a migration against this table, and the rows a retired gate leaves
    # behind are still part of the audit trail.
    kind: Mapped[str] = mapped_column(
        String(GATE_KIND_MAX_LENGTH),
        comment="Name of the `IGatePolicy` this hold belongs to",
    )
    status: Mapped[GateStatus] = mapped_column(
        comment="Whether this hold still blocks the release"
    )

    created: Mapped[datetime_now] = mapped_column(
        comment="When the hold was opened. The policy timeout is measured from here."
    )
    resolved: Mapped[datetime.datetime | None] = mapped_column(
        comment="When the hold stopped being pending. Null while pending."
    )

    note: Mapped[str | None] = mapped_column(
        comment="Human-readable explanation of the current status"
    )
    resolved_by: Mapped[str | None] = mapped_column(
        comment=(
            "A policy name for an automated decision, or a username for an "
            "administrative bypass"
        )
    )
    # Opaque to the mechanism: a policy records whatever evidence drove its
    # decision, and nothing here reads it.
    details: Mapped[dict | None] = mapped_column(JSONB)

    @property
    def blocking(self) -> bool:
        return self.status in BLOCKING_GATE_STATUSES
