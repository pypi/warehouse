# SPDX-License-Identifier: Apache-2.0
"""
Rename 'provider' to 'Publisher'

Revision ID: 0cb51a600b59
Revises: f93cf2d43974
Create Date: 2023-02-22 18:49:41.461379
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0cb51a600b59"
down_revision = "f93cf2d43974"


def upgrade():
    op.drop_index(
        "ix_pending_oidc_providers_added_by_id", table_name="pending_oidc_providers"
    )
    op.drop_index("ix_macaroons_oidc_provider_id", table_name="macaroons")
    op.drop_constraint(
        "macaroons_oidc_provider_id_fkey", "macaroons", type_="foreignkey"
    )
    op.drop_column("macaroons", "oidc_provider_id")
    op.drop_table("oidc_provider_project_association")
    op.drop_table("github_oidc_providers")
    op.drop_table("oidc_providers")
    op.drop_table("pending_github_oidc_providers")
    op.drop_table("pending_oidc_providers")

    op.create_table(
        "oidc_publishers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("discriminator", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "github_oidc_publishers",
        sa.Column("repository_name", sa.String(), nullable=True),
        sa.Column("repository_owner", sa.String(), nullable=True),
        sa.Column("repository_owner_id", sa.String(), nullable=True),
        sa.Column("workflow_filename", sa.String(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["oidc_publishers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "repository_name",
            "repository_owner",
            "workflow_filename",
            name="_github_oidc_publisher_uc",
        ),
    )
    op.create_table(
        "oidc_publisher_project_association",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("oidc_publisher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["oidc_publisher_id"],
            ["oidc_publishers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
        ),
        sa.PrimaryKeyConstraint("id", "oidc_publisher_id", "project_id"),
    )
    op.create_table(
        "pending_oidc_publishers",
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
    op.create_table(
        "pending_github_oidc_publishers",
        sa.Column("repository_name", sa.String(), nullable=True),
        sa.Column("repository_owner", sa.String(), nullable=True),
        sa.Column("repository_owner_id", sa.String(), nullable=True),
        sa.Column("workflow_filename", sa.String(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["pending_oidc_publishers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "repository_name",
            "repository_owner",
            "workflow_filename",
            name="_pending_github_oidc_publisher_uc",
        ),
    )
    op.create_index(
        op.f("ix_pending_oidc_publishers_added_by_id"),
        "pending_oidc_publishers",
        ["added_by_id"],
        unique=False,
    )
    op.add_column(
        "macaroons",
        sa.Column("oidc_publisher_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        op.f("ix_macaroons_oidc_publisher_id"),
        "macaroons",
        ["oidc_publisher_id"],
        unique=False,
    )
    op.create_foreign_key(
        None, "macaroons", "oidc_publishers", ["oidc_publisher_id"], ["id"]
    )

    # Macaroon -> (User XOR OIDCPublisher)
    op.create_check_constraint(
        "_user_xor_oidc_publisher_macaroon",
        table_name="macaroons",
        condition="(user_id::text IS NULL) <> (oidc_publisher_id::text IS NULL)",
    )


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
