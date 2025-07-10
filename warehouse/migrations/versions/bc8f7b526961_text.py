# SPDX-License-Identifier: Apache-2.0
"""
text

Revision ID: bc8f7b526961
Revises: 19ca1c78e613
Create Date: 2020-06-16 21:14:53.343466
"""

import sqlalchemy as sa

from alembic import op

revision = "bc8f7b526961"
down_revision = "19ca1c78e613"


def upgrade():
    op.add_column(
        "projects", sa.Column("total_size_limit", sa.BigInteger(), nullable=True)
    )


def downgrade():
    op.drop_column("projects", "total_size_limit")
