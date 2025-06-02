# SPDX-License-Identifier: Apache-2.0
"""
Create OrganizationApplication model

Revision ID: 5dcbd2bc748f
Revises: 646bc86a09b6
Create Date: 2023-06-02 22:38:01.308198
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "5dcbd2bc748f"
down_revision = "646bc86a09b6"


def upgrade():
    op.create_table(
        "organization_applications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "name", sa.Text(), nullable=False, comment="The account name used in URLS"
        ),
        sa.Column(
            "display_name", sa.Text(), nullable=False, comment="Display name used in UI"
        ),
        sa.Column(
            "orgtype",
            sa.Enum("Community", "Company", name="organizationtype"),
            nullable=False,
            comment="What type of organization such as Community or Company",
        ),
        sa.Column(
            "link_url",
            sa.Text(),
            nullable=False,
            comment="External URL associated with the organization",
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=False,
            comment=(
                "Description of the business or project the organization represents"
            ),
        ),
        sa.Column(
            "is_approved",
            sa.Boolean(),
            nullable=True,
            comment="Status of administrator approval of the request",
        ),
        sa.Column(
            "submitted_by_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="ID of the User which submitted the request",
        ),
        sa.Column(
            "submitted",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Datetime the request was submitted",
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="If the request was approved, ID of resulting Organization",
        ),
        sa.CheckConstraint(
            "link_url ~* '^https?://.*'::text",
            name="organization_applications_valid_link_url",
        ),
        sa.CheckConstraint(
            "name ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'::text",
            name="organization_applications_valid_name",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by_id"],
            ["users.id"],
            ondelete="CASCADE",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_organization_applications_submitted"),
        "organization_applications",
        ["submitted"],
        unique=False,
    )
    op.alter_column(
        "organizations",
        "name",
        existing_type=sa.TEXT(),
        comment="The account name used in URLS",
        existing_nullable=False,
    )
    op.alter_column(
        "organizations",
        "display_name",
        existing_type=sa.TEXT(),
        comment="Display name used in UI",
        existing_nullable=False,
    )
    op.alter_column(
        "organizations",
        "orgtype",
        existing_type=sa.TEXT(),
        comment="What type of organization such as Community or Company",
        existing_nullable=False,
    )
    op.alter_column(
        "organizations",
        "link_url",
        existing_type=sa.TEXT(),
        comment="External URL associated with the organization",
        existing_nullable=False,
    )
    op.alter_column(
        "organizations",
        "description",
        existing_type=sa.TEXT(),
        comment="Description of the business or project the organization represents",
        existing_nullable=False,
    )
    op.alter_column(
        "organizations",
        "is_approved",
        existing_type=sa.BOOLEAN(),
        comment="Status of administrator approval of the request",
        existing_nullable=True,
    )
    op.alter_column(
        "organizations",
        "is_active",
        existing_type=sa.BOOLEAN(),
        comment="When True, the organization is active and all features are available.",
        existing_nullable=False,
        existing_server_default=sa.text("false"),
    )
    op.alter_column(
        "organizations",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        comment="Datetime the organization was created.",
        existing_nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "organizations",
        "date_approved",
        existing_type=postgresql.TIMESTAMP(),
        comment="Datetime the organization was approved by administrators.",
        existing_nullable=True,
    )


def downgrade():
    op.alter_column(
        "organizations",
        "date_approved",
        existing_type=postgresql.TIMESTAMP(),
        comment=None,
        existing_comment="Datetime the organization was approved by administrators.",
        existing_nullable=True,
    )
    op.alter_column(
        "organizations",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        comment=None,
        existing_comment="Datetime the organization was created.",
        existing_nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "organizations",
        "is_active",
        existing_type=sa.BOOLEAN(),
        comment=None,
        existing_comment=(
            "When True, the organization is active and all features are available."
        ),
        existing_nullable=False,
        existing_server_default=sa.text("false"),
    )
    op.alter_column(
        "organizations",
        "is_approved",
        existing_type=sa.BOOLEAN(),
        comment=None,
        existing_comment="Status of administrator approval of the request",
        existing_nullable=True,
    )
    op.alter_column(
        "organizations",
        "description",
        existing_type=sa.TEXT(),
        comment=None,
        existing_comment=(
            "Description of the business or project the organization represents"
        ),
        existing_nullable=False,
    )
    op.alter_column(
        "organizations",
        "link_url",
        existing_type=sa.TEXT(),
        comment=None,
        existing_comment="External URL associated with the organization",
        existing_nullable=False,
    )
    op.alter_column(
        "organizations",
        "orgtype",
        existing_type=sa.TEXT(),
        comment=None,
        existing_comment="What type of organization such as Community or Company",
        existing_nullable=False,
    )
    op.alter_column(
        "organizations",
        "display_name",
        existing_type=sa.TEXT(),
        comment=None,
        existing_comment="Display name used in UI",
        existing_nullable=False,
    )
    op.alter_column(
        "organizations",
        "name",
        existing_type=sa.TEXT(),
        comment=None,
        existing_comment="The account name used in URLS",
        existing_nullable=False,
    )
    op.drop_index(
        op.f("ix_organization_applications_submitted"),
        table_name="organization_applications",
    )
    op.drop_table("organization_applications")
