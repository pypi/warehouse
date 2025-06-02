# SPDX-License-Identifier: Apache-2.0
"""
Move All User FKs to id instead of username

Revision ID: 5538f2d929dd
Revises: ee5b8f66a223
Create Date: 2018-11-06 08:16:12.099174
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "5538f2d929dd"
down_revision = "ee5b8f66a223"


def upgrade():
    op.add_column(
        "roles", sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.execute(
        """ UPDATE roles
            SET user_id = accounts_user.id
            FROM accounts_user
            WHERE roles.user_name = accounts_user.username
        """
    )
    op.alter_column("roles", "user_id", nullable=False)
    op.drop_constraint("roles_user_name_fkey", "roles", type_="foreignkey")
    op.create_foreign_key(
        None,
        "roles",
        "accounts_user",
        ["user_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )
    op.drop_index("roles_user_name_idx", table_name="roles")
    op.create_index("roles_user_id_idx", "roles", ["user_id"])
    op.drop_column("roles", "user_name")


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
