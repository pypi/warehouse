# SPDX-License-Identifier: Apache-2.0
"""
Drop date_approved column on Organization

Revision ID: 6de76386dbf4
Revises: 9986317d0010
Create Date: 2025-03-18 12:08:02.617345
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "6de76386dbf4"
down_revision = "9986317d0010"


def upgrade():
    op.drop_column("organizations", "date_approved")


def downgrade():
    op.add_column(
        "organizations",
        sa.Column(
            "date_approved",
            postgresql.TIMESTAMP(),
            autoincrement=False,
            nullable=True,
            comment="Datetime the organization was approved by administrators.",
        ),
    )
    op.execute("UPDATE organizations SET date_approved=created")
