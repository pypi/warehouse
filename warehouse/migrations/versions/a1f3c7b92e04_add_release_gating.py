# SPDX-License-Identifier: Apache-2.0
"""
Add release gating

`releases.gated` defaults to false, so every release that is currently
published stays published.

Revision ID: a1f3c7b92e04
Revises: c7e2a9d41f30
Create Date: 2026-10-18 14:30:00.000000
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a1f3c7b92e04"
down_revision = "c7e2a9d41f30"


def upgrade():
    # NOT NULL with a server default is a metadata-only change on PG 11+, so
    # this does not rewrite the releases table.
    op.add_column(
        "releases",
        sa.Column(
            "gated",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment=(
                "Denormalized from `release_gates`: true while any gate blocks. "
                "Only ever written through `IGateService`."
            ),
        ),
    )
    op.create_index(
        "releases_gated_idx",
        "releases",
        ["gated"],
        unique=False,
        postgresql_where=sa.text("gated"),
    )

    op.create_table(
        "release_gates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("release_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "kind",
            sa.String(64),
            nullable=False,
            comment="Name of the `IGatePolicy` this hold belongs to",
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "passed",
                "failed",
                "bypassed",
                "expired",
                name="gatestatus",
            ),
            nullable=False,
            comment="Whether this hold still blocks the release",
        ),
        sa.Column(
            "created",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
            comment=(
                "When the hold was opened. The policy timeout is measured from here."
            ),
        ),
        sa.Column(
            "resolved",
            sa.DateTime(),
            nullable=True,
            comment="When the hold stopped being pending. Null while pending.",
        ),
        sa.Column(
            "note",
            sa.String(),
            nullable=True,
            comment="Human-readable explanation of the current status",
        ),
        sa.Column(
            "resolved_by",
            sa.String(),
            nullable=True,
            comment=(
                "A policy name for an automated decision, or a username for an "
                "administrative bypass"
            ),
        ),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["release_id"],
            ["releases.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("release_id", "kind", name="_release_gate_kind_uc"),
    )
    op.create_index(
        op.f("ix_release_gates_release_id"), "release_gates", ["release_id"]
    )
    op.create_index("release_gates_status_idx", "release_gates", ["status"])
    op.create_index("release_gates_pending_created_idx", "release_gates", ["created"])


def downgrade():
    op.drop_index("release_gates_pending_created_idx", table_name="release_gates")
    op.drop_index("release_gates_status_idx", table_name="release_gates")
    op.drop_index(op.f("ix_release_gates_release_id"), table_name="release_gates")
    op.drop_table("release_gates")
    sa.Enum(name="gatestatus").drop(op.get_bind())

    op.drop_index("releases_gated_idx", table_name="releases")
    op.drop_column("releases", "gated")
