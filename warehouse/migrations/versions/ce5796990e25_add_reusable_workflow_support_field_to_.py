# SPDX-License-Identifier: Apache-2.0
"""
Add reusable workflow support field to GH Trusted Publishers

Revision ID: ce5796990e25
Revises: a3b1c4d5e6f7
Create Date: 2026-05-18 18:59:41.253478
"""

import sqlalchemy as sa

from alembic import op

revision = "ce5796990e25"
down_revision = "a3b1c4d5e6f7"


def upgrade():
    op.add_column(
        "github_oidc_publishers",
        sa.Column(
            "supports_legacy_reusable_workflows",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("github_oidc_publishers", "supports_legacy_reusable_workflows")
