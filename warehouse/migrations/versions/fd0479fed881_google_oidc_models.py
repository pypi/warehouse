# SPDX-License-Identifier: Apache-2.0
"""
Google OIDC models

Revision ID: fd0479fed881
Revises: d1771b942eb6
Create Date: 2023-05-02 17:45:43.772359
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "fd0479fed881"
down_revision = "d1771b942eb6"


def upgrade():
    op.create_table(
        "google_oidc_publishers",
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("sub", sa.String(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["oidc_publishers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", "sub", name="_google_oidc_publisher_uc"),
    )
    op.create_table(
        "pending_google_oidc_publishers",
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("sub", sa.String(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["pending_oidc_publishers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", "sub", name="_pending_google_oidc_publisher_uc"),
    )


def downgrade():
    op.drop_table("pending_google_oidc_publishers")
    op.drop_table("google_oidc_publishers")
