# SPDX-License-Identifier: Apache-2.0
"""
Add disallow-deletion AdminFlag

Revision ID: 8650482fb903
Revises: 34b18e18775c
Create Date: 2019-08-23 13:29:17.110252
"""

from alembic import op

revision = "8650482fb903"
down_revision = "34b18e18775c"


def upgrade():
    op.execute(
        """
        INSERT INTO admin_flags(id, description, enabled, notify)
        VALUES (
            'disallow-deletion',
            'Disallow ALL project and release deletions',
            FALSE,
            FALSE
        )
    """
    )


def downgrade():
    op.execute("DELETE FROM admin_flags WHERE id = 'disallow-deletion'")
