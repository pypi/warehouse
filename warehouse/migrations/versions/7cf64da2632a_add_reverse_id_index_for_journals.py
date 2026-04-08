# SPDX-License-Identifier: Apache-2.0
"""
Add reverse ID index for journals

Revision ID: 7cf64da2632a
Revises: 4c20f2342bba
Create Date: 2025-11-14 18:14:43.440919
"""

import sqlalchemy as sa

from alembic import op

revision = "7cf64da2632a"
down_revision = "4c20f2342bba"


def upgrade():
    # CREATE INDEX CONCURRENTLY cannot happen inside a transaction. We'll close
    # our transaction here and issue the statement.
    op.get_bind().commit()

    with op.get_context().autocommit_block():
        op.execute(sa.text("SET statement_timeout = 200000"))
        op.execute(sa.text("SET lock_timeout = 200000"))

        op.create_index(
            "journals_name_id_idx",
            "journals",
            ["name", sa.literal_column("id DESC")],
            unique=False,
            postgresql_concurrently=True,
        )


def downgrade():
    op.drop_index("journals_name_id_idx", table_name="journals")
