# SPDX-License-Identifier: Apache-2.0
"""
Add disabled-by-default Buildkite OIDC feature flag

Revision ID: a1c4b5219d5e
Revises: 45301e80ef72
Create Date: 2026-08-18 00:00:00.000000
"""

from alembic import op

revision = "a1c4b5219d5e"
down_revision = "45301e80ef72"


def upgrade():
    op.execute("""
        INSERT INTO admin_flags(id, description, enabled, notify)
        VALUES (
            'disallow-buildkite-oidc',
            'Disallow the Buildkite OIDC publisher',
            TRUE,
            FALSE
        )
        """)


def downgrade():
    op.execute("DELETE FROM admin_flags WHERE id = 'disallow-buildkite-oidc'")
