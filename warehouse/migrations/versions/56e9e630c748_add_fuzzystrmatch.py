# SPDX-License-Identifier: Apache-2.0
"""
Add fuzzystrmatch

Revision ID: 56e9e630c748
Revises: e82c3a017d60
Create Date: 2018-08-28 19:00:47.606523
"""

from alembic import op

revision = "56e9e630c748"
down_revision = "e82c3a017d60"


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS fuzzystrmatch")


def downgrade():
    pass
