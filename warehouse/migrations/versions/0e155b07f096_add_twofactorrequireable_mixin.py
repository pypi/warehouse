# SPDX-License-Identifier: Apache-2.0
"""
Add TwoFactorRequireable mixin

Revision ID: 0e155b07f096
Revises: 1b97443dea8a
Create Date: 2022-01-05 21:53:08.462640
"""

import sqlalchemy as sa

from alembic import op

revision = "0e155b07f096"
down_revision = "1b97443dea8a"


def upgrade():
    op.add_column(
        "projects",
        sa.Column(
            "owners_require_2fa",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "pypi_mandates_2fa",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("projects", "pypi_mandates_2fa")
    op.drop_column("projects", "owners_require_2fa")
