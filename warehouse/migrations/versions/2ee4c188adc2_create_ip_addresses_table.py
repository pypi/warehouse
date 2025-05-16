# SPDX-License-Identifier: Apache-2.0
"""
create ip_addresses_table

Revision ID: 2ee4c188adc2
Revises: adb74475e8a4
Create Date: 2022-11-08 14:50:20.300773
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "2ee4c188adc2"
down_revision = "adb74475e8a4"


def upgrade():
    op.create_table(
        "ip_addresses",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("ip_address", postgresql.INET, nullable=False),
        sa.Column(
            "is_banned", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "ban_reason",
            sa.Enum("authentication-attempts", name="banreason"),
            nullable=True,
        ),
        sa.Column("ban_date", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ip_address"),
    )
    op.create_index("bans_idx", "ip_addresses", ["is_banned"], unique=False)


def downgrade():
    op.drop_index("bans_idx", table_name="ip_addresses")
    op.drop_table("ip_addresses")
