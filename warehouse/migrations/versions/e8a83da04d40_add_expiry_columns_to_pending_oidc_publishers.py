# SPDX-License-Identifier: Apache-2.0
"""
Add expiry columns to pending_oidc_publishers

Revision ID: e8a83da04d40
Revises: b8e6e0867168
Create Date: 2026-04-09 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "e8a83da04d40"
down_revision = "b8e6e0867168"


def upgrade():
    op.add_column(
        "pending_oidc_publishers",
        sa.Column(
            "created",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "pending_oidc_publishers",
        sa.Column(
            "expiration_reminded",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("pending_oidc_publishers", "expiration_reminded")
    op.drop_column("pending_oidc_publishers", "created")
