# SPDX-License-Identifier: Apache-2.0
"""
Add SemaphoreCI OIDC models

Revision ID: 7a97c540ed60
Revises: 6c0f7fea7b1b
Create Date: 2025-11-04 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "7a97c540ed60"
down_revision = "6c0f7fea7b1b"


def upgrade():
    op.create_table(
        "semaphore_oidc_publishers",
        sa.Column("organization", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("project", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("repo_slug", sa.String(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["oidc_publishers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization",
            "organization_id",
            "project",
            "project_id",
            "repo_slug",
            name="_semaphore_oidc_publisher_uc",
        ),
    )
    op.create_table(
        "pending_semaphore_oidc_publishers",
        sa.Column("organization", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("project", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("repo_slug", sa.String(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["pending_oidc_publishers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization",
            "organization_id",
            "project",
            "project_id",
            "repo_slug",
            name="_pending_semaphore_oidc_publisher_uc",
        ),
    )


def downgrade():
    op.drop_table("pending_semaphore_oidc_publishers")
    op.drop_table("semaphore_oidc_publishers")
