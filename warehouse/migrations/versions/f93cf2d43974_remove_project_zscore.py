# SPDX-License-Identifier: Apache-2.0
"""
Remove Project.zscore

Revision ID: f93cf2d43974
Revises: 62601ddf674c
Create Date: 2023-01-24 20:41:03.489453
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f93cf2d43974"
down_revision = "62601ddf674c"


def upgrade():
    op.drop_column("projects", "zscore")


def downgrade():
    op.add_column(
        "projects",
        sa.Column(
            "zscore",
            postgresql.DOUBLE_PRECISION(precision=53),
            autoincrement=False,
            nullable=True,
        ),
    )
