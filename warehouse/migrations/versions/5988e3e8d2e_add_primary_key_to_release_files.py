# SPDX-License-Identifier: Apache-2.0
"""
Add Primary Key to Release Files

Revision ID: 5988e3e8d2e
Revises: 128a0ead322
Create Date: 2015-03-08 21:08:16.285082
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "5988e3e8d2e"
down_revision = "128a0ead322"


def upgrade():
    op.add_column(
        "release_files",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("release_files", "id")
