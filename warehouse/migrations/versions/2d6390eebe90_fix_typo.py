# SPDX-License-Identifier: Apache-2.0
"""
Fix typo

Revision ID: 2d6390eebe90
Revises: 08447ab49999
Create Date: 2018-11-12 03:05:20.555925
"""

from alembic import op

revision = "2d6390eebe90"
down_revision = "08447ab49999"


def upgrade():
    op.create_index(
        "journals_submitted_date_id_idx",
        "journals",
        ["submitted_date", "id"],
        unique=False,
    )
    op.drop_index("journakls_submitted_date_id_idx", table_name="journals")


def downgrade():
    op.create_index(
        "journakls_submitted_date_id_idx",
        "journals",
        ["submitted_date", "id"],
        unique=False,
    )
    op.drop_index("journals_submitted_date_id_idx", table_name="journals")
