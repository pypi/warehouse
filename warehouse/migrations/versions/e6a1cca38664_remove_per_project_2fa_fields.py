# SPDX-License-Identifier: Apache-2.0
"""
Remove per-project 2FA fields

Revision ID: e6a1cca38664
Revises: 0940ed80e40a
Create Date: 2024-01-03 16:51:45.896071
"""

import sqlalchemy as sa

from alembic import op

revision = "e6a1cca38664"
down_revision = "0940ed80e40a"


def upgrade():
    op.drop_column("projects", "owners_require_2fa")
    op.drop_column("projects", "pypi_mandates_2fa")


def downgrade():
    op.add_column(
        "projects",
        sa.Column(
            "pypi_mandates_2fa",
            sa.BOOLEAN(),
            server_default=sa.text("false"),
            autoincrement=False,
            nullable=False,
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "owners_require_2fa",
            sa.BOOLEAN(),
            server_default=sa.text("false"),
            autoincrement=False,
            nullable=False,
        ),
    )
