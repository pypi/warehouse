# SPDX-License-Identifier: Apache-2.0
"""
Add Macaroons

Revision ID: 5ea52744d154
Revises: a9cbb1025607
Create Date: 2018-07-16 06:45:31.152291
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "5ea52744d154"
down_revision = "a9cbb1025607"


def upgrade():
    op.create_table(
        "macaroons",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("description", sa.String(length=100), nullable=False),
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("last_used", sa.DateTime(), nullable=True),
        sa.Column(
            "caveats",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("key", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("macaroons")
