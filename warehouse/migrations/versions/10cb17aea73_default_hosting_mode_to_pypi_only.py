# SPDX-License-Identifier: Apache-2.0
"""
Default hosting mode to pypi-only

Revision ID: 10cb17aea73
Revises: 41abd35caa3
Create Date: 2015-09-03 01:18:55.288971
"""

from alembic import op

revision = "10cb17aea73"
down_revision = "41abd35caa3"


def upgrade():
    op.alter_column(
        "packages",
        "hosting_mode",
        server_default="pypi-only",
        existing_server_default="pypi-explicit",
    )


def downgrade():
    op.alter_column(
        "packages",
        "hosting_mode",
        server_default="pypi-explicit",
        existing_server_default="pypi-only",
    )
