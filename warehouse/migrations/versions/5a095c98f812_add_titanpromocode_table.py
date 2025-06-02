# SPDX-License-Identifier: Apache-2.0
"""
Add TitanPromoCode table

Revision ID: 5a095c98f812
Revises: b08bcde4183c
Create Date: 2022-03-02 02:56:08.154324
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "5a095c98f812"
down_revision = "b08bcde4183c"


def upgrade():
    op.create_table(
        "user_titan_codes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("distributed", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], initially="DEFERRED", deferrable=True
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(
        op.f("ix_user_titan_codes_user_id"),
        "user_titan_codes",
        ["user_id"],
        unique=True,
    )


def downgrade():
    op.drop_index(op.f("ix_user_titan_codes_user_id"), table_name="user_titan_codes")
    op.drop_table("user_titan_codes")
