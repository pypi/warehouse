# SPDX-License-Identifier: Apache-2.0
"""
Updated to newer Alembic mechanisms

Revision ID: b8fda0d7fbb5
Revises: 99291f0fe9c2
Create Date: 2016-12-12 00:16:49.783149
"""

from alembic import op

revision = "b8fda0d7fbb5"
down_revision = "99291f0fe9c2"


def upgrade():
    op.create_index(
        "accounts_email_user_id", "accounts_email", ["user_id"], unique=False
    )
    op.drop_constraint(
        "accounts_email_user_id_fkey", "accounts_email", type_="foreignkey"
    )
    op.create_foreign_key(
        None,
        "accounts_email",
        "accounts_user",
        ["user_id"],
        ["id"],
        initially="DEFERRED",
        deferrable=True,
    )
    op.create_index(
        "accounts_gpgkey_user_id", "accounts_gpgkey", ["user_id"], unique=False
    )
    op.drop_constraint(
        "accounts_gpgkey_user_id_fkey", "accounts_gpgkey", type_="foreignkey"
    )
    op.create_foreign_key(
        None,
        "accounts_gpgkey",
        "accounts_user",
        ["user_id"],
        ["id"],
        initially="DEFERRED",
        deferrable=True,
    )


def downgrade():
    op.drop_constraint(None, "accounts_gpgkey", type_="foreignkey")
    op.create_foreign_key(
        "accounts_gpgkey_user_id_fkey",
        "accounts_gpgkey",
        "accounts_user",
        ["user_id"],
        ["id"],
        deferrable=True,
    )
    op.drop_index("accounts_gpgkey_user_id", table_name="accounts_gpgkey")
    op.drop_constraint(None, "accounts_email", type_="foreignkey")
    op.create_foreign_key(
        "accounts_email_user_id_fkey",
        "accounts_email",
        "accounts_user",
        ["user_id"],
        ["id"],
        deferrable=True,
    )
    op.drop_index("accounts_email_user_id", table_name="accounts_email")
