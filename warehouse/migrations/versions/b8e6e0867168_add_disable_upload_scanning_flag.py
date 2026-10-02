# SPDX-License-Identifier: Apache-2.0
"""
Add disable-upload-scanning AdminFlag

Revision ID: b8e6e0867168
Revises: 28c1e0646708
Create Date: 2026-02-25
"""

from alembic import op

revision = "b8e6e0867168"
down_revision = "28c1e0646708"


def upgrade():
    op.execute("""
        INSERT INTO admin_flags(id, description, enabled, notify)
        VALUES (
            'disable-upload-scanning',
            'Disable YARA content scanning during uploads',
            FALSE,
            FALSE
        )
    """)


def downgrade():
    op.execute("DELETE FROM admin_flags WHERE id = 'disable-upload-scanning'")
