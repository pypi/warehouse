# SPDX-License-Identifier: Apache-2.0
"""
File events

Revision ID: d64193adcd10
Revises: eb736cb3236d
Create Date: 2023-03-15 17:36:12.321663
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d64193adcd10"
down_revision = "eb736cb3236d"


def upgrade():
    op.create_table(
        "file_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tag", sa.String(), nullable=False),
        sa.Column(
            "time", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("ip_address_string", sa.String(), nullable=True),
        sa.Column("additional", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip_address_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ip_address_id"],
            ["ip_addresses.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["release_files.id"], initially="DEFERRED", deferrable=True
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_file_events_source_id", "file_events", ["source_id"], unique=False
    )


def downgrade():
    op.drop_index("ix_file_events_source_id", table_name="file_events")
    op.drop_table("file_events")
