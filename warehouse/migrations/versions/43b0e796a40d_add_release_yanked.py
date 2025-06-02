# SPDX-License-Identifier: Apache-2.0
"""
Add Release.yanked

Revision ID: 43b0e796a40d
Revises: b265ed9eeb8a
Create Date: 2020-03-13 03:31:03.153039
"""

import sqlalchemy as sa

from alembic import op

revision = "43b0e796a40d"
down_revision = "b265ed9eeb8a"


def upgrade():
    op.add_column(
        "releases",
        sa.Column(
            "yanked", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )


def downgrade():
    op.drop_column("releases", "yanked")
