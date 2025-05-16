# SPDX-License-Identifier: Apache-2.0
"""
Add User.has_oidc_beta_access flag

Revision ID: cc06bd67a61b
Revises: 0cb51a600b59
Create Date: 2023-02-23 18:52:59.525595
"""

import sqlalchemy as sa

from alembic import op

revision = "cc06bd67a61b"
down_revision = "0cb51a600b59"


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "has_oidc_beta_access",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("users", "has_oidc_beta_access")
