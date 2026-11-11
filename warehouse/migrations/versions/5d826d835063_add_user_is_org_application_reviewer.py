# SPDX-License-Identifier: Apache-2.0
"""
Add User.is_org_application_reviewer

Revision ID: 5d826d835063
Revises: f555f02f7688
Create Date: 2026-10-21 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "5d826d835063"
down_revision = "f555f02f7688"


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "is_org_application_reviewer",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("users", "is_org_application_reviewer")
