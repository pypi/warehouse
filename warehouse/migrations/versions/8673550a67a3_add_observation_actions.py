# SPDX-License-Identifier: Apache-2.0
"""
Add Observation.actions

Revision ID: 8673550a67a3
Revises: 73c201ff90f3
Create Date: 2024-04-11 20:45:05.218380
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "8673550a67a3"
down_revision = "73c201ff90f3"


def upgrade():
    op.add_column(
        "project_observations",
        sa.Column(
            "actions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
            comment="Actions taken based on the observation",
        ),
    )
    op.add_column(
        "release_observations",
        sa.Column(
            "actions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
            comment="Actions taken based on the observation",
        ),
    )


def downgrade():
    op.drop_column("release_observations", "actions")
    op.drop_column("project_observations", "actions")
