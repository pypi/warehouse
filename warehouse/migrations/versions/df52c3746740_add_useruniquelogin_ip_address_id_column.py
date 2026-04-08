# SPDX-License-Identifier: Apache-2.0
"""
Add UserUniqueLogin.ip_address_id column

Revision ID: df52c3746740
Revises: a25f3d5186a9
Create Date: 2025-12-02 16:11:17.059400
"""

import sqlalchemy as sa

from alembic import op

revision = "df52c3746740"
down_revision = "a25f3d5186a9"


def upgrade():
    op.add_column(
        "user_unique_logins", sa.Column("ip_address_id", sa.UUID(), nullable=True)
    )
    op.create_index(
        op.f("ix_user_unique_logins_ip_address_id"),
        "user_unique_logins",
        ["ip_address_id"],
        unique=False,
    )
    op.create_foreign_key(
        None,
        "user_unique_logins",
        "ip_addresses",
        ["ip_address_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint(None, "user_unique_logins", type_="foreignkey")
    op.drop_index(
        op.f("ix_user_unique_logins_ip_address_id"), table_name="user_unique_logins"
    )
    op.drop_column("user_unique_logins", "ip_address_id")
