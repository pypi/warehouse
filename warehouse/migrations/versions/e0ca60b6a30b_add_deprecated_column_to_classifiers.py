# SPDX-License-Identifier: Apache-2.0
"""
Add 'deprecated' column to classifiers

Revision ID: e0ca60b6a30b
Revises: 6714f3f04f0f
Create Date: 2018-04-18 23:24:13.009357
"""

import sqlalchemy as sa

from alembic import op

revision = "e0ca60b6a30b"
down_revision = "6714f3f04f0f"


def upgrade():
    op.add_column(
        "trove_classifiers",
        sa.Column(
            "deprecated", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )


def downgrade():
    op.drop_column("trove_classifiers", "deprecated")
