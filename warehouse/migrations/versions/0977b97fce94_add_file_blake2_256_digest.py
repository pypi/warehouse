# SPDX-License-Identifier: Apache-2.0
"""
Add File.blake2_256_digest

Revision ID: 0977b97fce94
Revises: f46672a776f1
Create Date: 2016-04-18 20:40:22.101245
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects.postgresql import CITEXT

revision = "0977b97fce94"
down_revision = "f46672a776f1"


def upgrade():
    op.add_column(
        "release_files", sa.Column("blake2_256_digest", CITEXT(), nullable=True)
    )
    op.create_unique_constraint(None, "release_files", ["blake2_256_digest"])
    op.create_check_constraint(
        None, "release_files", "sha256_digest ~* '^[A-F0-9]{64}$'"
    )


def downgrade():
    raise RuntimeError("Cannot Go Backwards In Time.")
