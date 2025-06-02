# SPDX-License-Identifier: Apache-2.0
"""
add published field

Revision ID: 6cac7b706953
Revises: 2a2c32c47a8f
Create Date: 2025-01-22 08:49:17.030343
"""

import sqlalchemy as sa

from alembic import op

revision = "6cac7b706953"
down_revision = "2a2c32c47a8f"


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text("SET statement_timeout = 120000"))
    conn.execute(sa.text("SET lock_timeout = 120000"))

    op.add_column(
        "releases",
        sa.Column(
            "published", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
    )


def downgrade():
    op.drop_column("releases", "published")
