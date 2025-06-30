# SPDX-License-Identifier: Apache-2.0
"""
add manual password reset prohibition

Revision ID: 08ccc59d9857
Revises: 10825786b3df
Create Date: 2021-07-13 14:40:16.604041
"""

import sqlalchemy as sa

from alembic import op

revision = "08ccc59d9857"
down_revision = "10825786b3df"


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "prohibit_password_reset",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("users", "prohibit_password_reset")
