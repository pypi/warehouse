# SPDX-License-Identifier: Apache-2.0
"""
Remove useless index

Revision ID: 7750037b351a
Revises: f449e5bff5a5
Create Date: 2016-12-17 21:10:27.781900
"""

from alembic import op

revision = "7750037b351a"
down_revision = "f449e5bff5a5"


def upgrade():
    op.drop_index("release_files_name_idx", table_name="release_files")


def downgrade():
    op.create_index("release_files_name_idx", "release_files", ["name"], unique=False)
