# SPDX-License-Identifier: Apache-2.0
"""
Add primary key to Dependency

Revision ID: 5ff0c99c94
Revises: 312040efcfe
Create Date: 2015-07-20 19:50:55.153532
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "5ff0c99c94"
down_revision = "312040efcfe"


def upgrade():
    op.add_column(
        "release_dependencies",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("release_dependencies", "id")
