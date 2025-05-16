# SPDX-License-Identifier: Apache-2.0
"""
Add read-only AdminFlag

Revision ID: 6418f7d86a4b
Revises: 5dda74213989
Create Date: 2018-03-23 20:51:31.558587
"""

from alembic import op

revision = "6418f7d86a4b"
down_revision = "bf73e785eed9"


def upgrade():
    op.execute(
        """
        INSERT INTO warehouse_admin_flag(id, description, enabled, notify)
        VALUES (
            'read-only',
            'Read-only mode: Any write operations will have no effect',
            FALSE,
            TRUE
        )
    """
    )


def downgrade():
    op.execute("DELETE FROM warehouse_admin_flag WHERE id = 'read-only'")
