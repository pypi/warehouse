# SPDX-License-Identifier: Apache-2.0
"""
Add Maintainer API keys

Revision ID: 1a2c1f2294ef
Revises: 5b1c8e7f2a9d
Create Date: 2026-10-08 13:37:14.779195
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "1a2c1f2294ef"
down_revision = "5b1c8e7f2a9d"


def upgrade():
    op.create_table(
        "api_keys",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("hashed_key", sa.String(length=64), nullable=False),
        sa.Column("last_four", sa.String(length=4), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("expires", sa.DateTime(), nullable=False),
        sa.Column("revoked", sa.DateTime(), nullable=True),
        sa.Column("last_used", sa.DateTime(), nullable=True),
        # TODO: Unused until expiry reminder emails exist.
        sa.Column("expiry_notified", sa.DateTime(), nullable=True),
        sa.Column("final_notice_sent", sa.DateTime(), nullable=True),
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.CheckConstraint(
            "expires <= created + interval '366 days'",
            name="api_keys_max_lifetime",
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hashed_key"),
    )
    op.create_index(
        op.f("ix_api_keys_created_by_id"), "api_keys", ["created_by_id"], unique=False
    )
    op.create_index(op.f("ix_api_keys_user_id"), "api_keys", ["user_id"], unique=False)


def downgrade():
    op.drop_table("api_keys")
