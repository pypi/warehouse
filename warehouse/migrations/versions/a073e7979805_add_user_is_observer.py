# SPDX-License-Identifier: Apache-2.0
"""
Add User.is_observer

Revision ID: 5224f11972be
Revises: 812e14a4cddf
Create Date: 2024-01-18 23:48:27.127394
"""

import sqlalchemy as sa

from alembic import op

revision = "a073e7979805"
down_revision = "812e14a4cddf"


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "is_observer",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="Is this user allowed to add Observations?",
        ),
    )


def downgrade():
    op.drop_column("users", "is_observer")
