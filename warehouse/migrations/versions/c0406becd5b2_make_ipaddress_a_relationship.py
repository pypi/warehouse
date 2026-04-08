# SPDX-License-Identifier: Apache-2.0
"""
Make IpAddress a relationship

Revision ID: c0406becd5b2
Revises: be443e514e3e
Create Date: 2025-12-09 14:43:01.645356
"""

import sqlalchemy as sa

from alembic import op

revision = "c0406becd5b2"
down_revision = "be443e514e3e"


def upgrade():
    op.drop_constraint(
        op.f("_user_unique_logins_user_id_ip_address_uc"),
        "user_unique_logins",
        type_="unique",
    )
    op.drop_index(
        op.f("user_unique_logins_user_id_ip_address_idx"),
        table_name="user_unique_logins",
    )
    op.create_unique_constraint(
        "_user_unique_logins_user_id_ip_address_id_uc",
        "user_unique_logins",
        ["user_id", "ip_address_id"],
    )
    op.create_index(
        "user_unique_logins_user_id_ip_address_id_idx",
        "user_unique_logins",
        ["user_id", "ip_address_id"],
        unique=True,
    )
    op.drop_column("user_unique_logins", "ip_address")


def downgrade():
    op.add_column(
        "user_unique_logins",
        sa.Column("ip_address", sa.VARCHAR(), autoincrement=False, nullable=False),
    )
    op.drop_index(
        "user_unique_logins_user_id_ip_address_id_idx", table_name="user_unique_logins"
    )
    op.drop_constraint(
        "_user_unique_logins_user_id_ip_address_id_uc",
        "user_unique_logins",
        type_="unique",
    )
    op.create_index(
        op.f("user_unique_logins_user_id_ip_address_idx"),
        "user_unique_logins",
        ["user_id", "ip_address"],
        unique=True,
    )
    op.create_unique_constraint(
        op.f("_user_unique_logins_user_id_ip_address_uc"),
        "user_unique_logins",
        ["user_id", "ip_address"],
        postgresql_nulls_not_distinct=False,
    )
