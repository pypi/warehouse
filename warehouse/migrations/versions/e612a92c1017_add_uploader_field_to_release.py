# SPDX-License-Identifier: Apache-2.0
"""
Add uploader field to Release

Revision ID: e612a92c1017
Revises: 5538f2d929dd
Create Date: 2018-11-06 16:22:01.484362
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e612a92c1017"
down_revision = "5538f2d929dd"


def upgrade():
    op.add_column(
        "releases",
        sa.Column("uploader_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        None,
        "releases",
        "accounts_user",
        ["uploader_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="SET NULL",
    )
    op.create_index("ix_releases_uploader_id", "releases", ["uploader_id"])


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
