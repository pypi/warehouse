# SPDX-License-Identifier: Apache-2.0
"""
Switch to a UUID based primary key for User

Revision ID: 8c8be2c0e69e
Revises: 039f45e2dbf9
Create Date: 2016-07-01 18:20:42.072664
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "8c8be2c0e69e"
down_revision = "039f45e2dbf9"


def upgrade():
    # Add a new column which is going to hold all of our new IDs for this table
    # with a temporary name until we can rename it.
    op.add_column(
        "accounts_user",
        sa.Column(
            "new_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )

    # Add a column to tables that refer to accounts_user so they can be updated
    # to refer to it.
    op.add_column(
        "accounts_email",
        sa.Column("new_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "accounts_gpgkey",
        sa.Column("new_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # Update our referring tables so that their new column points to the
    # correct user account.
    op.execute(""" UPDATE accounts_email
            SET new_user_id = accounts_user.new_id
            FROM accounts_user
            WHERE accounts_email.user_id = accounts_user.id
        """)
    op.execute(""" UPDATE accounts_gpgkey
            SET new_user_id = accounts_user.new_id
            FROM accounts_user
            WHERE accounts_gpgkey.user_id = accounts_user.id
        """)

    # Disallow any NULL values in our referring tables
    op.alter_column("accounts_email", "new_user_id", nullable=False)
    op.alter_column("accounts_gpgkey", "new_user_id", nullable=False)

    # Delete our existing fields and move our new fields into their old places.
    op.drop_constraint("accounts_email_user_id_fkey", "accounts_email")
    op.drop_column("accounts_email", "user_id")
    op.alter_column("accounts_email", "new_user_id", new_column_name="user_id")

    op.drop_constraint("accounts_gpgkey_user_id_fkey", "accounts_gpgkey")
    op.drop_column("accounts_gpgkey", "user_id")
    op.alter_column("accounts_gpgkey", "new_user_id", new_column_name="user_id")

    # Switch the primary key from the old to the new field, drop the old name,
    # and rename the new field into it's place.
    op.drop_constraint("accounts_user_pkey", "accounts_user")
    op.create_primary_key(None, "accounts_user", ["new_id"])
    op.drop_column("accounts_user", "id")
    op.alter_column("accounts_user", "new_id", new_column_name="id")

    # Finally, Setup our foreign key constraints for our referring tables.
    op.create_foreign_key(
        None, "accounts_email", "accounts_user", ["user_id"], ["id"], deferrable=True
    )
    op.create_foreign_key(
        None, "accounts_gpgkey", "accounts_user", ["user_id"], ["id"], deferrable=True
    )


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
