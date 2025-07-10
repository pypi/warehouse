# SPDX-License-Identifier: Apache-2.0
"""
Add Release.keywords_array column

Revision ID: 208d494aac68
Revises: fd06c4fe2f97
Create Date: 2024-08-02 19:02:01.760253
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "208d494aac68"
down_revision = "fd06c4fe2f97"


def upgrade():
    op.add_column(
        "releases",
        sa.Column(
            "keywords_array",
            postgresql.ARRAY(sa.String()),
            nullable=True,
            comment=(
                "Array of keywords. Null indicates no keywords were supplied by "
                "the uploader."
            ),
        ),
    )


def downgrade():
    op.drop_column("releases", "keywords_array")
