# SPDX-License-Identifier: Apache-2.0
"""
create verified field for ReleaseUrl

Revision ID: 26455e3712a2
Revises: 208d494aac68
Create Date: 2024-04-30 18:40:17.149050
"""

import sqlalchemy as sa

from alembic import op

revision = "26455e3712a2"
down_revision = "208d494aac68"


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text("SET statement_timeout = 120000"))
    conn.execute(sa.text("SET lock_timeout = 120000"))
    op.add_column(
        "release_urls",
        sa.Column(
            "verified", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )


def downgrade():
    op.drop_column("release_urls", "verified")
