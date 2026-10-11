# SPDX-License-Identifier: Apache-2.0
"""
Add Release Lifecycle Status

Revision ID: a3b1c4d5e6f7
Revises: e8a83da04d40
Create Date: 2026-05-12 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a3b1c4d5e6f7"
down_revision = "e8a83da04d40"


def upgrade():
    op.execute("SET statement_timeout = 11000")
    op.execute("SET lock_timeout = 10000")

    op.add_column(
        "releases",
        sa.Column(
            "lifecycle_status",
            postgresql.ENUM(
                "quarantine-enter",
                "quarantine-exit",
                "archived",
                "archived-noindex",
                name="lifecyclestatus",
                create_type=False,
            ),
            nullable=True,
            comment="Lifecycle status can change release visibility and access",
        ),
    )
    op.add_column(
        "releases",
        sa.Column(
            "lifecycle_status_changed",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=True,
            comment="When the lifecycle status was last changed",
        ),
    )
    op.add_column(
        "releases",
        sa.Column(
            "lifecycle_status_note",
            sa.String(),
            nullable=True,
            comment="Note about the lifecycle status",
        ),
    )
    op.create_index(
        "releases_lifecycle_status_idx",
        "releases",
        ["lifecycle_status"],
        unique=False,
    )


def downgrade():
    op.drop_index("releases_lifecycle_status_idx", table_name="releases")
    op.drop_column("releases", "lifecycle_status_note")
    op.drop_column("releases", "lifecycle_status_changed")
    op.drop_column("releases", "lifecycle_status")
