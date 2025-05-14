# SPDX-License-Identifier: Apache-2.0
"""
Add MissingDatasetFile

Revision ID: 77d52a945a5f
Revises: 12a43f12cc18
Create Date: 2025-01-17 16:56:09.082853
"""

import sqlalchemy as sa

from alembic import op

revision = "77d52a945a5f"
down_revision = "12a43f12cc18"


def upgrade():
    op.create_table(
        "missing_dataset_files",
        sa.Column("file_id", sa.UUID(), nullable=False),
        sa.Column("processed", sa.Boolean(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["release_files.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("missing_dataset_files")
