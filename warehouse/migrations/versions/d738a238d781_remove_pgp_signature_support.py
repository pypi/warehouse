# SPDX-License-Identifier: Apache-2.0
"""
Remove PGP signature support

Revision ID: d738a238d781
Revises: ab536b1853f0
Create Date: 2023-05-21 14:46:11.845339
"""

from alembic import op

revision = "d738a238d781"
down_revision = "ab536b1853f0"


def upgrade():
    op.drop_column("release_files", "has_signature")


def downgrade():
    raise RuntimeError("Cannot undelete data!")
