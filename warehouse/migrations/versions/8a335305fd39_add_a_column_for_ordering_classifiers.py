# SPDX-License-Identifier: Apache-2.0
"""
Add a column for ordering classifiers

Revision ID: 8a335305fd39
Revises: 4490777c984f
Create Date: 2022-07-22 00:06:40.868910
"""

import sqlalchemy as sa

from alembic import op

revision = "8a335305fd39"
down_revision = "4490777c984f"


def upgrade():
    op.add_column(
        "trove_classifiers", sa.Column("ordering", sa.Integer(), nullable=True)
    )


def downgrade():
    op.drop_column("trove_classifiers", "ordering")
