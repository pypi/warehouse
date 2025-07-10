# SPDX-License-Identifier: Apache-2.0
"""
Remove User.has_oidc_beta_access column

Revision ID: d1771b942eb6
Revises: 75ba94852cd1
Create Date: 2023-04-20 17:33:44.571959
"""

import sqlalchemy as sa

from alembic import op

revision = "d1771b942eb6"
down_revision = "75ba94852cd1"


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text("SET statement_timeout = 120000"))
    conn.execute(sa.text("SET lock_timeout = 120000"))
    op.drop_column("users", "has_oidc_beta_access")


def downgrade():
    op.add_column(
        "users",
        sa.Column(
            "has_oidc_beta_access",
            sa.BOOLEAN(),
            server_default=sa.text("false"),
            autoincrement=False,
            nullable=False,
        ),
    )
