# SPDX-License-Identifier: Apache-2.0
"""
add two_factor and update users

Revision ID: 42f0409bb702
Revises: c0c0544354e7
Create Date: 2019-03-28 21:01:52.980989
"""

import sqlalchemy as sa

from alembic import op

revision = "42f0409bb702"
down_revision = "c4a1ee483bb3"


def upgrade():
    op.add_column(
        "users", sa.Column("totp_secret", sa.LargeBinary(length=20), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column(
            "two_factor_allowed", sa.Boolean, nullable=False, server_default=sa.false()
        ),
    )


def downgrade():
    op.drop_column("users", "totp_secret")
    op.drop_column("users", "two_factor_allowed")
