# SPDX-License-Identifier: Apache-2.0
"""
Add 'avatar_hidden' column to User model

Revision ID: d0f67adbcb80
Revises: fe2e3d22b3fa
Create Date: 2022-09-28 16:02:44.054680
"""

import sqlalchemy as sa

from alembic import op

revision = "d0f67adbcb80"
down_revision = "fe2e3d22b3fa"


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "hide_avatar", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )


def downgrade():
    op.drop_column("users", "hide_avatar")
