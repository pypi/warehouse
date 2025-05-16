# SPDX-License-Identifier: Apache-2.0
"""
Add disallow-new-upload AdminFlag

Revision ID: ee4c59b2ef3a
Revises: 8650482fb903
Create Date: 2019-08-23 22:34:29.180163
"""

from alembic import op

revision = "ee4c59b2ef3a"
down_revision = "8650482fb903"


def upgrade():
    op.execute(
        """
        INSERT INTO admin_flags(id, description, enabled, notify)
        VALUES (
            'disallow-new-upload',
            'Disallow ALL new uploads',
            FALSE,
            FALSE
        )
    """
    )


def downgrade():
    op.execute("DELETE FROM admin_flags WHERE id = 'disallow-new-upload'")
