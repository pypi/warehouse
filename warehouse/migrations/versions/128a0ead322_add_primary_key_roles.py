# SPDX-License-Identifier: Apache-2.0
"""
Add primary key to roles

Revision ID: 128a0ead322
Revises: 283c68f2ab2
Create Date: 2015-02-18 18:48:23.131652
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "128a0ead322"
down_revision = "283c68f2ab2"


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.add_column(
        "roles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("roles", "id")
