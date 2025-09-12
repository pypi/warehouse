# SPDX-License-Identifier: Apache-2.0
"""
Add a path column to store the location of the file

Revision ID: 6ff880c36cd9
Revises: f392e419ea1b
Create Date: 2016-01-06 20:37:45.190833
"""

import sqlalchemy as sa

from alembic import op

revision = "6ff880c36cd9"
down_revision = "f392e419ea1b"


def upgrade():
    op.add_column("release_files", sa.Column("path", sa.Text(), nullable=True))
    op.create_unique_constraint(None, "release_files", ["path"])


def downgrade():
    op.drop_constraint(None, "release_files", type_="unique")
    op.drop_column("release_files", "path")
