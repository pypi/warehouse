# SPDX-License-Identifier: Apache-2.0
"""
Create OpenID Connect 'sub' column for Google Users Migration

Revision ID: 18e4cf2bb3e
Revises: 116be7c87e1
Create Date: 2015-11-07 22:43:21.589230
"""

import sqlalchemy as sa

from alembic import op

revision = "18e4cf2bb3e"
down_revision = "116be7c87e1"


def upgrade():
    op.add_column("openids", sa.Column("sub", sa.Text()))

    op.create_index("openids_subkey", "openids", [sa.text("sub")], unique=True)


def downgrade():
    op.drop_index("openids_subkey", table_name="openids")
    op.drop_column("openids", "sub")
