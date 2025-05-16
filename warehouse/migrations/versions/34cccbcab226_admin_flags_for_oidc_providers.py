# SPDX-License-Identifier: Apache-2.0
"""
admin flags for oidc providers

Revision ID: 34cccbcab226
Revises: 5dcbd2bc748f
Create Date: 2023-06-06 02:29:32.374813
"""

from alembic import op

revision = "34cccbcab226"
down_revision = "5dcbd2bc748f"


def upgrade():
    op.execute(
        """
        INSERT INTO admin_flags(id, description, enabled, notify)
        VALUES (
            'disallow-github-oidc',
            'Disallow the GitHub OIDC provider',
            FALSE,
            FALSE
        )
        """
    )
    op.execute(
        """
        INSERT INTO admin_flags(id, description, enabled, notify)
        VALUES (
            'disallow-google-oidc',
            'Disallow the Google OIDC provider',
            FALSE,
            FALSE
        )
        """
    )


def downgrade():
    op.execute("DELETE FROM admin_flags WHERE id = 'disallow-github-oidc'")
    op.execute("DELETE FROM admin_flags WHERE id = 'disallow-google-oidc'")
