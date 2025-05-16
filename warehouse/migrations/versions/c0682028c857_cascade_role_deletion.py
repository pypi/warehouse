# SPDX-License-Identifier: Apache-2.0
"""
Cascade Role deletion

Revision ID: c0682028c857
Revises: 1fdf5dc6bbf3
Create Date: 2018-03-08 19:15:01.860863
"""

from alembic import op

revision = "c0682028c857"
down_revision = "1fdf5dc6bbf3"


def upgrade():
    op.drop_constraint("roles_package_name_fkey", "roles", type_="foreignkey")
    op.drop_constraint("roles_user_name_fkey", "roles", type_="foreignkey")
    op.create_foreign_key(
        "roles_package_name_fkey",
        "roles",
        "packages",
        ["package_name"],
        ["name"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "roles_user_name_fkey",
        "roles",
        "accounts_user",
        ["user_name"],
        ["username"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint(None, "roles", type_="foreignkey")
    op.drop_constraint(None, "roles", type_="foreignkey")
    op.create_foreign_key(
        "roles_user_name_fkey",
        "roles",
        "accounts_user",
        ["user_name"],
        ["username"],
        onupdate="CASCADE",
    )
    op.create_foreign_key(
        "roles_package_name_fkey",
        "roles",
        "packages",
        ["package_name"],
        ["name"],
        onupdate="CASCADE",
    )
