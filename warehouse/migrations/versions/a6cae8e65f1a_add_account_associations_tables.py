# SPDX-License-Identifier: Apache-2.0
"""
Add account associations with OAuth inheritance

Revision ID: a6cae8e65f1a
Revises: c0406becd5b2
Create Date: 2025-12-15 16:18:09.637486
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

from warehouse.utils.db.types import TZDateTime

revision = "a6cae8e65f1a"
down_revision = "c0406becd5b2"


def upgrade():
    op.create_table(
        "account_associations",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("updated", TZDateTime(), nullable=True),
        sa.Column(
            "user_id",
            sa.UUID(),
            nullable=False,
            comment="PyPI user who owns this account association",
        ),
        sa.Column(
            "association_type",
            sa.String(length=50),
            nullable=False,
            comment="Polymorphic discriminator for association subtype",
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=True,
            comment="Additional metadata specific to the association type",
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_account_associations_user_id"),
        "account_associations",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "oauth_account_associations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "service",
            sa.String(length=50),
            nullable=False,
            comment="External OAuth provider name (github, gitlab, google, etc.)",
        ),
        sa.Column(
            "external_user_id",
            sa.String(length=255),
            nullable=False,
            comment="User identifier from external OAuth provider",
        ),
        sa.Column(
            "external_username",
            sa.String(length=255),
            nullable=False,
            comment="Username or display name from external OAuth provider",
        ),
        sa.ForeignKeyConstraint(
            ["id"], ["account_associations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "service",
            "external_user_id",
            name="oauth_account_associations_service_external_user_id",
        ),
    )


def downgrade():
    # Drop the OAuth associations table first (due to foreign key)
    op.drop_table("oauth_account_associations")

    # Drop indexes
    op.drop_index(
        op.f("ix_account_associations_user_id"), table_name="account_associations"
    )

    # Drop the base associations table
    op.drop_table("account_associations")
