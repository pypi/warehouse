# SPDX-License-Identifier: Apache-2.0
"""
Add yanked_date column to Release

Revision ID: 3f0c896f7f06
Revises: ff0b39808d7c
Create Date: 2026-07-20 15:16:42.776686
"""

import sqlalchemy as sa

from alembic import op

revision = "3f0c896f7f06"
down_revision = "ff0b39808d7c"


def upgrade():
    op.add_column(
        "releases",
        sa.Column(
            "yanked_date",
            sa.DateTime(),
            nullable=True,
            comment="When the release was yanked",
        ),
    )


def downgrade():
    op.drop_column("releases", "yanked_date")
