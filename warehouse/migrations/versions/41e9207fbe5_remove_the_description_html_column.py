# SPDX-License-Identifier: Apache-2.0
"""
Remove the description_html column

Revision ID: 41e9207fbe5
Revises: 49b93c346db
Create Date: 2015-06-03 19:44:43.269987
"""

from alembic import op

revision = "41e9207fbe5"
down_revision = "49b93c346db"


def upgrade():
    op.drop_column("releases", "description_html")


def downgrade():
    raise RuntimeError(f"Cannot downgrade past {revision!r}")
