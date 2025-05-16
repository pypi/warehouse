# SPDX-License-Identifier: Apache-2.0
"""
Add Banner.dismissable

Revision ID: b34fa465a67c
Revises: 186f076eb60b
Create Date: 2023-11-16 21:12:13.737681
"""

import sqlalchemy as sa

from alembic import op

revision = "b34fa465a67c"
down_revision = "186f076eb60b"


def upgrade():
    op.add_column(
        "banners",
        sa.Column(
            "dismissable", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )


def downgrade():
    op.drop_column("banners", "dismissable")
