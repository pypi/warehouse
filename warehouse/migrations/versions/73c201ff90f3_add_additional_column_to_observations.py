# SPDX-License-Identifier: Apache-2.0
"""
Add additional column to Observations

Revision ID: 73c201ff90f3
Revises: 34c3175f4bea
Create Date: 2024-04-11 18:22:08.928952
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "73c201ff90f3"
down_revision = "34c3175f4bea"


def upgrade():
    op.add_column(
        "project_observations",
        sa.Column(
            "additional",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
            comment="Additional data for the observation",
        ),
    )
    op.add_column(
        "release_observations",
        sa.Column(
            "additional",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
            comment="Additional data for the observation",
        ),
    )


def downgrade():
    op.drop_column("release_observations", "additional")
    op.drop_column("project_observations", "additional")
