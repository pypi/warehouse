# SPDX-License-Identifier: Apache-2.0
"""
Remove caveats to permissions

Revision ID: 84262e097c26
Revises: f345394c444f
Create Date: 2022-04-05 18:35:57.325801
"""

from alembic import op

revision = "84262e097c26"
down_revision = "f345394c444f"


def upgrade():
    op.alter_column("macaroons", "caveats", new_column_name="permissions_caveat")


def downgrade():
    op.alter_column("macaroons", "permissions_caveat", new_column_name="caveats")
