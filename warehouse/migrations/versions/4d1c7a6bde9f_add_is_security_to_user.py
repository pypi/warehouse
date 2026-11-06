# SPDX-License-Identifier: Apache-2.0
"""
Add User.is_security

Revision ID: 4d1c7a6bde9f
Revises: e7c1c116be9a
"""

import sqlalchemy as sa

from alembic import op

revision = "4d1c7a6bde9f"
down_revision = "e7c1c116be9a"


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "is_security",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("users", "is_security")
