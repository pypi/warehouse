# SPDX-License-Identifier: Apache-2.0
"""
Add RecoveryCode.burned timestamp

Revision ID: 29a8901a4635
Revises: 0e155b07f096
Create Date: 2022-02-09 00:05:18.323250
"""

import sqlalchemy as sa

from alembic import op

revision = "29a8901a4635"
down_revision = "0e155b07f096"


def upgrade():
    op.add_column(
        "user_recovery_codes", sa.Column("burned", sa.DateTime(), nullable=True)
    )


def downgrade():
    op.drop_column("user_recovery_codes", "burned")
