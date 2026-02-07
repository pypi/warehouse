# SPDX-License-Identifier: Apache-2.0
"""
Refactor UserUniqueLogin to use mapped_column

Revision ID: 4c20f2342bba
Revises: 6c0f7fea7b1b
Create Date: 2025-07-29 00:55:39.682180
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "4c20f2342bba"
down_revision = "6c0f7fea7b1b"


def upgrade():
    sa.Enum("pending", "confirmed", name="uniqueloginstatus").create(op.get_bind())
    op.create_table(
        "user_unique_logins",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("ip_address", sa.String(), nullable=False),
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "last_used",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "device_information", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "confirmed",
                name="uniqueloginstatus",
                create_type=False,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "ip_address", name="_user_unique_logins_user_id_ip_address_uc"
        ),
    )
    op.create_index(
        op.f("ix_user_unique_logins_user_id"),
        "user_unique_logins",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "user_unique_logins_user_id_ip_address_idx",
        "user_unique_logins",
        ["user_id", "ip_address"],
        unique=True,
    )


def downgrade():
    op.drop_index(
        op.f("ix_user_unique_logins_user_id"), table_name="user_unique_logins"
    )
    op.drop_index(
        "user_unique_logins_user_id_ip_address_idx", table_name="user_unique_logins"
    )
    op.drop_table("user_unique_logins")
    sa.Enum("pending", "confirmed", name="uniqueloginstatus").drop(op.get_bind())
