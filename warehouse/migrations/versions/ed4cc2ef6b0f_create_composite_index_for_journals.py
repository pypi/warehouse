# SPDX-License-Identifier: Apache-2.0
"""
Create composite index for journals

Revision ID: ed4cc2ef6b0f
Revises: 48a7b9ee15af
Create Date: 2025-01-13 19:08:43.774259
"""

import sqlalchemy as sa

from alembic import op

revision = "ed4cc2ef6b0f"
down_revision = "5bc11bd312e5"


def upgrade():
    op.get_bind().commit()
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = 4000")
        op.execute("SET statement_timeout = 5000")
        op.create_index(
            "journals_submitted_by_and_reverse_date_idx",
            "journals",
            ["submitted_by", sa.text("submitted_date DESC")],
            unique=False,
            if_not_exists=True,
            postgresql_concurrently=True,
        )


def downgrade():
    op.drop_index("journals_submitted_by_and_reverse_date_idx", table_name="journals")
