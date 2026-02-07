# SPDX-License-Identifier: Apache-2.0
"""
Add observation_kid to prohibited_project_names

Revision ID: db7633e75422
Revises: 635b80625fc9
Create Date: 2025-03-03 20:21:55.738828
"""

import sqlalchemy as sa

from alembic import op

revision = "db7633e75422"
down_revision = "635b80625fc9"


def upgrade():
    op.add_column(
        "prohibited_project_names",
        sa.Column(
            "observation_kind",
            sa.String(),
            nullable=True,
            comment="If this was created via an observation, the kind of observation",
        ),
    )


def downgrade():
    op.drop_column("prohibited_project_names", "observation_kind")
