# SPDX-License-Identifier: Apache-2.0
"""
add pending OIDC provider hierarchy

Revision ID: aa3a4757f33a
Revises: 43bf0b6badcb
Create Date: 2022-11-18 22:19:55.133681
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "aa3a4757f33a"
down_revision = "43bf0b6badcb"


def upgrade():
    op.create_table(
        "pending_oidc_providers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("discriminator", sa.String(), nullable=True),
        sa.Column("project_name", sa.String(), nullable=False),
        sa.Column("added_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["added_by_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pending_oidc_providers_added_by_id"),
        "pending_oidc_providers",
        ["added_by_id"],
        unique=False,
    )
    op.create_table(
        "pending_github_oidc_providers",
        sa.Column("repository_name", sa.String(), nullable=True),
        sa.Column("repository_owner", sa.String(), nullable=True),
        sa.Column("repository_owner_id", sa.String(), nullable=True),
        sa.Column("workflow_filename", sa.String(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["pending_oidc_providers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "repository_name",
            "repository_owner",
            "workflow_filename",
            name="_pending_github_oidc_provider_uc",
        ),
    )


def downgrade():
    op.drop_table("pending_github_oidc_providers")
    op.drop_index(
        op.f("ix_pending_oidc_providers_added_by_id"),
        table_name="pending_oidc_providers",
    )
    op.drop_table("pending_oidc_providers")
