# SPDX-License-Identifier: Apache-2.0
"""
remove Provenance.provenance_digest

Revision ID: 2af8015830dd
Revises: a8050411bc65
Create Date: 2024-09-23 17:09:16.199384
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "2af8015830dd"
down_revision = "a8050411bc65"


def upgrade():
    op.drop_column("provenance", "provenance_digest")


def downgrade():
    op.add_column(
        "provenance",
        sa.Column(
            "provenance_digest",
            postgresql.CITEXT(),
            autoincrement=False,
            nullable=False,
        ),
    )
