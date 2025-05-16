# SPDX-License-Identifier: Apache-2.0
"""
Remove MissingDatasetFile

Revision ID: 2a2c32c47a8f
Revises: 77d52a945a5f
Create Date: 2025-01-21 15:49:29.129691
"""

import sqlalchemy as sa

from alembic import op

revision = "2a2c32c47a8f"
down_revision = "77d52a945a5f"


def upgrade():
    op.drop_table("missing_dataset_files")


def downgrade():
    op.create_table(
        "missing_dataset_files",
        sa.Column("file_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("processed", sa.BOOLEAN(), autoincrement=False, nullable=True),
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["release_files.id"], name="missing_dataset_files_file_id_fkey"
        ),
        sa.PrimaryKeyConstraint("id", name="missing_dataset_files_pkey"),
    )
