# SPDX-License-Identifier: Apache-2.0
"""
update expires for pending user_unique_logins

Revision ID: a25f3d5186a9
Revises: 537b63a29cea
Create Date: 2025-11-20 19:09:40.492013
"""

from alembic import op

revision = "a25f3d5186a9"
down_revision = "537b63a29cea"


def upgrade():
    op.execute("""
        UPDATE user_unique_logins
        SET expires = created + INTERVAL '6 hours'
        WHERE status = 'pending' AND expires IS NULL
        """)


def downgrade():
    pass
