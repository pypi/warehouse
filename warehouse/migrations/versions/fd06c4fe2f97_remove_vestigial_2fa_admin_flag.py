# SPDX-License-Identifier: Apache-2.0
"""
Remove vestigial 2FA admin flag

Revision ID: fd06c4fe2f97
Revises: bb6943882aa9
Create Date: 2024-08-07 15:39:12.970946
"""

from alembic import op

revision = "fd06c4fe2f97"
down_revision = "bb6943882aa9"


def upgrade():
    op.execute("DELETE FROM admin_flags WHERE id = '2fa-required'")


def downgrade():
    op.execute("""
        INSERT INTO admin_flags(id, description, enabled, notify)
        VALUES (
            '2fa-required',
            'Require 2FA for all users',
            FALSE,
            FALSE
        )
    """)
