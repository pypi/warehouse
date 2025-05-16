# SPDX-License-Identifier: Apache-2.0
"""
Add a server default for submitted_date

Revision ID: 477bc785c999
Revises: 6a03266b2d
Create Date: 2015-12-16 16:19:59.419186
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "477bc785c999"
down_revision = "6a03266b2d"


def upgrade():
    op.alter_column(
        "journals", "submitted_date", server_default=sa.func.now(), nullable=False
    )


def downgrade():
    op.alter_column(
        "journals",
        "submitted_date",
        existing_type=postgresql.TIMESTAMP(),
        server_default=None,
        nullable=True,
    )
