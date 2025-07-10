# SPDX-License-Identifier: Apache-2.0
"""
Add notify column to AdminFlag

Revision ID: bf73e785eed9
Revises: 5dda74213989
Create Date: 2018-03-23 21:20:05.834821
"""

import sqlalchemy as sa

from alembic import op

revision = "bf73e785eed9"
down_revision = "5dda74213989"


def upgrade():
    op.add_column(
        "warehouse_admin_flag",
        sa.Column(
            "notify", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )


def downgrade():
    op.drop_column("warehouse_admin_flag", "notify")
