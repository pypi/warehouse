# SPDX-License-Identifier: Apache-2.0
"""
Add a column for tracking why a user was disabled

Revision ID: 4e7d5154cb0c
Revises: 68a00c174ba5
Create Date: 2018-08-14 01:20:03.996141
"""

import sqlalchemy as sa

from alembic import op

revision = "4e7d5154cb0c"
down_revision = "68a00c174ba5"


DisableReason = sa.Enum("password compromised", name="disable_reason")


def upgrade():
    DisableReason.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "accounts_user", sa.Column("disabled_for", DisableReason, nullable=True)
    )


def downgrade():
    op.drop_column("accounts_user", "disabled_for")
    DisableReason.drop(op.get_bind())
