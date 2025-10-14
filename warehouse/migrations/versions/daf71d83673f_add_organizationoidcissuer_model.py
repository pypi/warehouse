# SPDX-License-Identifier: Apache-2.0
"""
Add OrganizationOIDCIssuer model

Revision ID: daf71d83673f
Revises: 6aacc97aea2e
Create Date: 2025-10-09 19:08:36.888994
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "daf71d83673f"
down_revision = "6aacc97aea2e"


def upgrade():
    sa.Enum("github", "gitlab", "google", "activestate", name="oidcissuertype").create(
        op.get_bind()
    )
    op.create_table(
        "organization_oidc_issuers",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column(
            "issuer_type",
            postgresql.ENUM(
                "github",
                "gitlab",
                "google",
                "activestate",
                name="oidcissuertype",
                create_type=False,
            ),
            nullable=False,
            comment="Type of OIDC issuer",
        ),
        sa.Column(
            "issuer_url",
            sa.String(),
            nullable=False,
            comment="Custom OIDC issuer URL (e.g., https://gitlab.company.com)",
        ),
        sa.Column(
            "created",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Datetime when the issuer was added",
        ),
        sa.Column(
            "created_by_id",
            sa.UUID(),
            nullable=False,
            comment="Admin user who created the issuer mapping",
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "issuer_type",
            "issuer_url",
            name="_organization_oidc_issuers_org_type_url_uc",
        ),
    )
    op.create_index(
        "organization_oidc_issuers_issuer_url_idx",
        "organization_oidc_issuers",
        ["issuer_url"],
        unique=False,
    )
    op.create_index(
        "organization_oidc_issuers_organization_id_idx",
        "organization_oidc_issuers",
        ["organization_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "organization_oidc_issuers_organization_id_idx",
        table_name="organization_oidc_issuers",
    )
    op.drop_index(
        "organization_oidc_issuers_issuer_url_idx",
        table_name="organization_oidc_issuers",
    )
    op.drop_table("organization_oidc_issuers")
    sa.Enum("github", "gitlab", "google", "activestate", name="oidcissuertype").drop(
        op.get_bind()
    )
