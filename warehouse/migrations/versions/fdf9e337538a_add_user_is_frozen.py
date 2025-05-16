# SPDX-License-Identifier: Apache-2.0
"""
Add User.is_frozen

Revision ID: fdf9e337538a
Revises: 19cf76d2d459
Create Date: 2022-03-21 17:02:22.924858
"""

import sqlalchemy as sa

from alembic import op

revision = "fdf9e337538a"
down_revision = "19cf76d2d459"


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "is_frozen", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )


def downgrade():
    op.drop_column("users", "is_frozen")
