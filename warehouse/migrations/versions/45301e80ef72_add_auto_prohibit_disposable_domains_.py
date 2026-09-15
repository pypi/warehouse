# SPDX-License-Identifier: Apache-2.0
"""
add AUTO_PROHIBIT_DISPOSABLE_DOMAINS flag

Revision ID: 45301e80ef72
Revises: 964076d0c4ad
Create Date: 2026-08-26 00:00:00.000000
"""

from alembic import op

revision = "45301e80ef72"
down_revision = "964076d0c4ad"


def upgrade():
    op.execute("""
        INSERT INTO admin_flags(id, description, enabled, notify)
        VALUES (
            'auto-prohibit-disposable-domains',
            'Automatically prohibit email domains reported as disposable providers',
            FALSE,
            FALSE
        )
    """)


def downgrade():
    op.execute("DELETE FROM admin_flags WHERE id = 'auto-prohibit-disposable-domains'")
