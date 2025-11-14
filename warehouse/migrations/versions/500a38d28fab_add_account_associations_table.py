# SPDX-License-Identifier: Apache-2.0
"""
Add account_associations table

Revision ID: 500a38d28fab
Revises: 4c20f2342bba
Create Date: 2025-11-12 17:25:42.687250
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

from warehouse.utils.db.types import TZDateTime

revision = "500a38d28fab"
down_revision = "4c20f2342bba"


def upgrade():
    op.create_table(
        "account_associations",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("updated", TZDateTime(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "service",
            sa.String(length=50),
            nullable=False,
            comment="External service name (e.g., 'github')",
        ),
        sa.Column(
            "external_user_id",
            sa.String(length=255),
            nullable=False,
            comment="User ID from external service",
        ),
        sa.Column(
            "external_username",
            sa.String(length=255),
            nullable=False,
            comment="Username from external service",
        ),
        sa.Column(
            "access_token",
            sa.String(),
            nullable=True,
            comment="Encrypted OAuth access token",
        ),
        sa.Column(
            "refresh_token",
            sa.String(),
            nullable=True,
            comment="Encrypted OAuth refresh token",
        ),
        sa.Column(
            "token_expires_at",
            TZDateTime(),
            nullable=True,
            comment="When the access token expires",
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=True,
            comment="Service-specific metadata (profile info, scopes, etc.)",
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "service", "external_user_id", name="account_associations_service_external"
        ),
    )
    op.create_index(
        "account_associations_user_service",
        "account_associations",
        ["user_id", "service"],
        unique=False,
    )
    op.create_index(
        op.f("ix_account_associations_user_id"),
        "account_associations",
        ["user_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_account_associations_user_id"), table_name="account_associations"
    )
    op.drop_index(
        "account_associations_user_service", table_name="account_associations"
    )
    op.drop_table("account_associations")
