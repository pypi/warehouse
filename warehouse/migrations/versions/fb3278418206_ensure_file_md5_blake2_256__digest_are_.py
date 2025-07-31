# SPDX-License-Identifier: Apache-2.0
"""
Ensure File.{md5,blake2_256}_digest are not nullable

Revision ID: fb3278418206
Revises: 0977b97fce94
Create Date: 2016-04-25 11:09:54.284023
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects.postgresql import CITEXT

revision = "fb3278418206"
down_revision = "0977b97fce94"


def upgrade():
    op.alter_column(
        "release_files",
        "blake2_256_digest",
        existing_type=CITEXT(),
        nullable=False,
    )
    op.alter_column(
        "release_files", "md5_digest", existing_type=sa.TEXT(), nullable=False
    )


def downgrade():
    op.alter_column(
        "release_files", "md5_digest", existing_type=sa.TEXT(), nullable=True
    )
    op.alter_column(
        "release_files",
        "blake2_256_digest",
        existing_type=CITEXT(),
        nullable=True,
    )
