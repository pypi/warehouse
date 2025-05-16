# SPDX-License-Identifier: Apache-2.0
"""
Make PendingOIDCPublisher.added_by_id non-nullable

Revision ID: 75ba94852cd1
Revises: f7cd7a943caa
Create Date: 2023-04-14 18:21:38.683694
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "75ba94852cd1"
down_revision = "f7cd7a943caa"


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text("SET statement_timeout = 120000"))
    conn.execute(sa.text("SET lock_timeout = 120000"))
    op.alter_column(
        "pending_oidc_publishers",
        "added_by_id",
        existing_type=postgresql.UUID(),
        nullable=False,
    )


def downgrade():
    op.alter_column(
        "pending_oidc_publishers",
        "added_by_id",
        existing_type=postgresql.UUID(),
        nullable=True,
    )
