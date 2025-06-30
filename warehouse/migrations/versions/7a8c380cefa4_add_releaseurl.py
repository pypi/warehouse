# SPDX-License-Identifier: Apache-2.0
"""
add ReleaseURL

Revision ID: 7a8c380cefa4
Revises: d1c00b634ac8
Create Date: 2022-06-10 22:02:49.522320
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "7a8c380cefa4"
down_revision = "d1c00b634ac8"


def upgrade():
    op.create_table(
        "release_urls",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("release_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["release_id"], ["releases.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("release_id", "name"),
    )
    op.create_index(
        op.f("ix_release_urls_release_id"), "release_urls", ["release_id"], unique=False
    )


def downgrade():
    op.drop_index(op.f("ix_release_urls_release_id"), table_name="release_urls")
    op.drop_table("release_urls")
