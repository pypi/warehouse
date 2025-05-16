# SPDX-License-Identifier: Apache-2.0
"""
Admin Flag: 2fa-required

Revision ID: 0940ed80e40a
Revises: 4297620f7b41
Create Date: 2023-12-05 23:44:58.113194
"""

from alembic import op

revision = "0940ed80e40a"
down_revision = "4297620f7b41"


def upgrade():
    op.execute(
        """
        INSERT INTO admin_flags(id, description, enabled, notify)
        VALUES (
            '2fa-required',
            'Require 2FA for all users',
            FALSE,
            FALSE
        )
    """
    )


def downgrade():
    op.execute("DELETE FROM admin_flags WHERE id = '2fa-required'")
