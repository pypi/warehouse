# SPDX-License-Identifier: Apache-2.0
"""
add description-content-type field

Revision ID: 5dda74213989
Revises: 2730e54f8717
Create Date: 2017-09-08 21:15:55.822175
"""

import sqlalchemy as sa

from alembic import op

revision = "5dda74213989"
down_revision = "2730e54f8717"


def upgrade():
    op.add_column(
        "releases", sa.Column("description_content_type", sa.Text(), nullable=True)
    )


def downgrade():
    op.drop_column("releases", "description_content_type")
