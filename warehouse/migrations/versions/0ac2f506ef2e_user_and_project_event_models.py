# SPDX-License-Identifier: Apache-2.0
"""
User and Project event models

Revision ID: 0ac2f506ef2e
Revises: d83f20495c10
Create Date: 2019-07-31 21:50:43.407231
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0ac2f506ef2e"
down_revision = "d83f20495c10"


def upgrade():
    op.create_table(
        "project_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag", sa.String(), nullable=False),
        sa.Column(
            "time", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("ip_address", sa.String(), nullable=False),
        sa.Column("additional", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], initially="DEFERRED", deferrable=True
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "user_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag", sa.String(), nullable=False),
        sa.Column(
            "time", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("ip_address", sa.String(), nullable=False),
        sa.Column("additional", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], initially="DEFERRED", deferrable=True
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("user_events")
    op.drop_table("project_events")
