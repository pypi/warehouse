# SPDX-License-Identifier: Apache-2.0
"""
Add Index on Release.created

Revision ID: 41abd35caa3
Revises: 3af8d0006ba
Create Date: 2015-08-24 23:16:07.674157
"""

import sqlalchemy as sa

from alembic import op

revision = "41abd35caa3"
down_revision = "3af8d0006ba"


def upgrade():
    op.create_index(
        "release_created_idx", "releases", [sa.text("created DESC")], unique=False
    )


def downgrade():
    op.drop_index("release_created_idx", table_name="releases")
