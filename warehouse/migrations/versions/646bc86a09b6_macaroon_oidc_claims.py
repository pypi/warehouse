# SPDX-License-Identifier: Apache-2.0
"""
macaroon oidc claims

Revision ID: 646bc86a09b6
Revises: 60e6b0dd0f47
Create Date: 2023-06-01 16:50:32.765849
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "646bc86a09b6"
down_revision = "60e6b0dd0f47"


def upgrade():
    op.add_column(
        "macaroons",
        sa.Column("additional", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade():
    op.drop_column("macaroons", "additional")
