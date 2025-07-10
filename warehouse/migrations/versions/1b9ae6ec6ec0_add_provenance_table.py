# SPDX-License-Identifier: Apache-2.0
"""
add provenance table

Revision ID: 1b9ae6ec6ec0
Revises: dcf1e3986782
Create Date: 2024-09-03 23:39:30.853147
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "1b9ae6ec6ec0"
down_revision = "dcf1e3986782"


def upgrade():
    op.create_table(
        "provenance",
        sa.Column("file_id", sa.UUID(), nullable=False),
        sa.Column(
            "provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("provenance_digest", postgresql.CITEXT(), nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["release_files.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("provenance")
