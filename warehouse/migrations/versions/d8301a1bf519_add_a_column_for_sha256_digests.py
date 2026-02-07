# SPDX-License-Identifier: Apache-2.0
"""
add a column for sha256 digests

Revision ID: d8301a1bf519
Revises: 477bc785c999
Create Date: 2016-01-04 13:51:16.931595
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects.postgresql import CITEXT

revision = "d8301a1bf519"
down_revision = "477bc785c999"


def upgrade():
    op.add_column("release_files", sa.Column("sha256_digest", CITEXT(), nullable=True))
    op.create_unique_constraint(None, "release_files", ["sha256_digest"])
    op.create_check_constraint(
        None, "release_files", "sha256_digest ~* '^[A-F0-9]{64}$'"
    )


def downgrade():
    op.drop_constraint(None, "release_files", type_="check")
    op.drop_constraint(None, "release_files", type_="unique")
    op.drop_column("release_files", "sha256_digest")
