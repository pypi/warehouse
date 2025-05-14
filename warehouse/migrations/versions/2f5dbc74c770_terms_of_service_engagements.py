# SPDX-License-Identifier: Apache-2.0
"""
terms of service engagements

Revision ID: 2f5dbc74c770
Revises: 6cac7b706953
Create Date: 2025-02-20 13:35:44.331611
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

from warehouse.utils.db.types import TZDateTime

revision = "2f5dbc74c770"
down_revision = "6cac7b706953"


def upgrade():
    sa.Enum(
        "flashed", "notified", "viewed", "agreed", name="termsofserviceengagement"
    ).create(op.get_bind())
    op.create_table(
        "organization_terms_of_service_engagements",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("revision", sa.String(), nullable=False),
        sa.Column("created", TZDateTime(), nullable=False),
        sa.Column(
            "engagement",
            postgresql.ENUM(
                "flashed",
                "notified",
                "viewed",
                "agreed",
                name="termsofserviceengagement",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "organization_terms_of_service_engagements_org_id_revision_idx",
        "organization_terms_of_service_engagements",
        ["organization_id", "revision"],
        unique=False,
    )
    op.create_table(
        "user_terms_of_service_engagements",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("revision", sa.String(), nullable=False),
        sa.Column("created", TZDateTime(), nullable=False),
        sa.Column(
            "engagement",
            postgresql.ENUM(
                "flashed",
                "notified",
                "viewed",
                "agreed",
                name="termsofserviceengagement",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "user_terms_of_service_engagements_user_id_revision_idx",
        "user_terms_of_service_engagements",
        ["user_id", "revision"],
        unique=False,
    )
    op.drop_index(
        "organization_terms_of_service_agreements_organization_id_idx",
        table_name="organization_terms_of_service_agreements",
    )
    op.drop_table("organization_terms_of_service_agreements")


def downgrade():
    op.create_table(
        "organization_terms_of_service_agreements",
        sa.Column("organization_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("agreed", postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
        sa.Column(
            "notified", postgresql.TIMESTAMP(), autoincrement=False, nullable=True
        ),
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="organization_terms_of_service_agreements_organization_id_fkey",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id", name="organization_terms_of_service_agreements_pkey"
        ),
    )
    op.create_index(
        "organization_terms_of_service_agreements_organization_id_idx",
        "organization_terms_of_service_agreements",
        ["organization_id"],
        unique=False,
    )
    op.drop_index(
        "user_terms_of_service_engagements_user_id_revision_idx",
        table_name="user_terms_of_service_engagements",
    )
    op.drop_table("user_terms_of_service_engagements")
    op.drop_index(
        "organization_terms_of_service_engagements_org_id_revision_idx",
        table_name="organization_terms_of_service_engagements",
    )
    op.drop_table("organization_terms_of_service_engagements")
    sa.Enum(
        "flashed", "notified", "viewed", "agreed", name="termsofserviceengagement"
    ).drop(op.get_bind())
