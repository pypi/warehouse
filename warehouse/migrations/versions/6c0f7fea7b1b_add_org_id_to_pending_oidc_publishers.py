# SPDX-License-Identifier: Apache-2.0
"""
Add Org ID to pending_oidc_publishers

Revision ID: 6c0f7fea7b1b
Revises: daf71d83673f
Create Date: 2025-11-04 23:29:08.395688
"""

import sqlalchemy as sa

from alembic import op

revision = "6c0f7fea7b1b"
down_revision = "daf71d83673f"


def upgrade():
    op.add_column(
        "pending_oidc_publishers",
        sa.Column("organization_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        op.f("ix_pending_oidc_publishers_organization_id"),
        "pending_oidc_publishers",
        ["organization_id"],
        unique=False,
    )
    op.create_foreign_key(
        None, "pending_oidc_publishers", "organizations", ["organization_id"], ["id"]
    )


def downgrade():
    op.drop_constraint(None, "pending_oidc_publishers", type_="foreignkey")
    op.drop_index(
        op.f("ix_pending_oidc_publishers_organization_id"),
        table_name="pending_oidc_publishers",
    )
    op.drop_column("pending_oidc_publishers", "organization_id")
