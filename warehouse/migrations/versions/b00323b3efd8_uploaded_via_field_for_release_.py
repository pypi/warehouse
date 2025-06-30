# SPDX-License-Identifier: Apache-2.0
"""
uploaded_via field for Release and Files

Revision ID: b00323b3efd8
Revises: f2a453c96ded
Create Date: 2018-07-25 17:29:01.995083
"""

import sqlalchemy as sa

from alembic import op

revision = "b00323b3efd8"
down_revision = "f2a453c96ded"


def upgrade():
    op.add_column("release_files", sa.Column("uploaded_via", sa.Text(), nullable=True))
    op.add_column("releases", sa.Column("uploaded_via", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("releases", "uploaded_via")
    op.drop_column("release_files", "uploaded_via")
