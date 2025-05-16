# SPDX-License-Identifier: Apache-2.0
"""
Add is_support to User

Revision ID: bb6943882aa9
Revises: c79e12731fcd
Create Date: 2024-07-15 13:55:49.978586
"""

import sqlalchemy as sa

from alembic import op

revision = "bb6943882aa9"
down_revision = "c79e12731fcd"


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "is_support", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )


def downgrade():
    op.drop_column("users", "is_support")
