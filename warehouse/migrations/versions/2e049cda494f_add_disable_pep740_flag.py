# SPDX-License-Identifier: Apache-2.0
"""
add DISABLE_PEP740 flag

Revision ID: 2e049cda494f
Revises: f204918656f1
Create Date: 2024-09-05 15:15:58.703955
"""

from alembic import op

revision = "2e049cda494f"
down_revision = "f204918656f1"


def upgrade():
    op.execute("""
        INSERT INTO admin_flags(id, description, enabled, notify)
        VALUES (
            'disable-pep740',
            'Disable PEP 740 support.',
            FALSE,
            FALSE
        )
    """)


def downgrade():
    op.execute("DELETE FROM admin_flags WHERE id = 'disable-pep740'")
