# SPDX-License-Identifier: Apache-2.0
"""
remove two_factor_allowed

Revision ID: e1b493d3b171
Revises: 9ca7d5668af4
Create Date: 2019-05-20 20:39:28.616037
"""

import sqlalchemy as sa

from alembic import op

revision = "e1b493d3b171"
down_revision = "9ca7d5668af4"


def upgrade():
    op.drop_column("users", "two_factor_allowed")


def downgrade():
    op.add_column(
        "users",
        sa.Column(
            "two_factor_allowed",
            sa.BOOLEAN(),
            server_default=sa.text("false"),
            autoincrement=False,
            nullable=False,
        ),
    )
