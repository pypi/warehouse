# SPDX-License-Identifier: Apache-2.0
"""
mandate sha256 hashes for all files

Revision ID: f392e419ea1b
Revises: d8301a1bf519
Create Date: 2016-01-04 16:20:50.428491
"""

from alembic import op

revision = "f392e419ea1b"
down_revision = "d8301a1bf519"


def upgrade():
    op.alter_column("release_files", "sha256_digest", nullable=False)


def downgrade():
    op.alter_column("release_files", "sha256_digest", nullable=True)
