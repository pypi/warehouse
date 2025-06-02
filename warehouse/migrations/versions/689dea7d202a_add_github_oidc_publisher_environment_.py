# SPDX-License-Identifier: Apache-2.0
"""
add GitHub OIDC publisher environment constraint

Revision ID: 689dea7d202a
Revises: d142f435bb39
Create Date: 2023-04-11 17:57:08.941312
"""

import sqlalchemy as sa

from alembic import op

revision = "689dea7d202a"
down_revision = "d142f435bb39"


def upgrade():
    op.add_column(
        "github_oidc_publishers", sa.Column("environment", sa.String(), nullable=True)
    )
    op.add_column(
        "pending_github_oidc_publishers",
        sa.Column("environment", sa.String(), nullable=True),
    )


def downgrade():
    op.drop_column("pending_github_oidc_publishers", "environment")
    op.drop_column("github_oidc_publishers", "environment")
