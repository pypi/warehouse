# SPDX-License-Identifier: Apache-2.0
"""
Add a column to project to record the zscore

Revision ID: 5b3f9e687d94
Revises: 7750037b351a
Create Date: 2017-03-10 02:14:12.402080
"""

import sqlalchemy as sa

from alembic import op

revision = "5b3f9e687d94"
down_revision = "7750037b351a"


def upgrade():
    op.add_column("packages", sa.Column("zscore", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("packages", "zscore")
