# SPDX-License-Identifier: Apache-2.0
"""
Add METADATA digest column to Release Files

Revision ID: 2b2f58288de1
Revises: fd0479fed881
Create Date: 2023-05-11 14:25:53.582849
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects.postgresql import CITEXT

revision = "2b2f58288de1"
down_revision = "fd0479fed881"


def upgrade():
    op.add_column(
        "release_files",
        sa.Column("metadata_file_sha256_digest", CITEXT(), nullable=True),
    )
    op.add_column(
        "release_files",
        sa.Column("metadata_file_blake2_256_digest", CITEXT(), nullable=True),
    )


def downgrade():
    op.drop_column("release_files", "metadata_file_blake2_256_digest")
    op.drop_column("release_files", "metadata_file_sha256_digest")
