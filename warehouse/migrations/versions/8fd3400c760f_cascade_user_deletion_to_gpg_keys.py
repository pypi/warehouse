# SPDX-License-Identifier: Apache-2.0
"""
Cascade User deletion to GPG keys

Revision ID: 8fd3400c760f
Revises: c0302a8a0878
Create Date: 2018-03-09 23:27:06.222073
"""

from alembic import op

revision = "8fd3400c760f"
down_revision = "c0302a8a0878"


def upgrade():
    op.drop_constraint(
        "accounts_gpgkey_user_id_fkey", "accounts_gpgkey", type_="foreignkey"
    )
    op.create_foreign_key(
        "accounts_gpgkey_user_id_fkey",
        "accounts_gpgkey",
        "accounts_user",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
        initially="DEFERRED",
        deferrable=True,
    )


def downgrade():
    op.drop_constraint(
        "accounts_gpgkey_user_id_fkey", "accounts_gpgkey", type_="foreignkey"
    )
    op.create_foreign_key(
        "accounts_gpgkey_user_id_fkey",
        "accounts_gpgkey",
        "accounts_user",
        ["user_id"],
        ["id"],
        initially="DEFERRED",
        deferrable=True,
    )
