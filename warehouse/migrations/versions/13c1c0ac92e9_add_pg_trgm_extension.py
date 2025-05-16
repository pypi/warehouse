# SPDX-License-Identifier: Apache-2.0
"""
add pg_trgm extension

Revision ID: 13c1c0ac92e9
Revises: c8384ca429fc
Create Date: 2025-04-29 08:37:33.788528
"""

from alembic import op

revision = "13c1c0ac92e9"
down_revision = "c8384ca429fc"


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade():
    pass
