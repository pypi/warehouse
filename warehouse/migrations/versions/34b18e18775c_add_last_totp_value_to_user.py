# SPDX-License-Identifier: Apache-2.0
"""
add last totp value to user

Revision ID: 34b18e18775c
Revises: 0ac2f506ef2e
Create Date: 2019-08-15 21:28:47.621282
"""

import sqlalchemy as sa

from alembic import op

revision = "34b18e18775c"
down_revision = "0ac2f506ef2e"


def upgrade():
    op.add_column("users", sa.Column("last_totp_value", sa.String(), nullable=True))


def downgrade():
    op.drop_column("users", "last_totp_value")
