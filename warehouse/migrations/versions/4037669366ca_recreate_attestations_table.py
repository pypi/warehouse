# SPDX-License-Identifier: Apache-2.0
"""
recreate attestations table

Revision ID: 4037669366ca
Revises: 606abd3b8e7f
Create Date: 2024-08-21 20:33:53.489489
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "4037669366ca"
down_revision = "606abd3b8e7f"


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
