# SPDX-License-Identifier: Apache-2.0
"""
create Attestations table

Revision ID: 7f0c9f105f44
Revises: 26455e3712a2
Create Date: 2024-07-25 15:49:01.993869
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "7f0c9f105f44"
down_revision = "26455e3712a2"


def upgrade():
    op.create_table(
        "attestation",
        sa.Column("file_id", sa.UUID(), nullable=False),
        sa.Column(
            "attestation_file_blake2_digest", postgresql.CITEXT(), nullable=False
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["release_files.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("attestation")
