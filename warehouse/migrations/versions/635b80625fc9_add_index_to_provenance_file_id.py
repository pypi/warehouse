# SPDX-License-Identifier: Apache-2.0
"""
Add index to Provenance.file_id

Revision ID: 635b80625fc9
Revises: 2f5dbc74c770
Create Date: 2025-02-28 17:41:58.763011
"""

from alembic import op

revision = "635b80625fc9"
down_revision = "2f5dbc74c770"


def upgrade():
    # CREATE INDEX CONCURRENTLY cannot happen inside a transaction. We'll close
    # our transaction here and issue the statement.
    op.get_bind().commit()
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_provenance_file_id",
            "provenance",
            ["file_id"],
            unique=False,
            postgresql_concurrently=True,
        )


def downgrade():
    op.drop_index(
        "ix_provenance_file_id", table_name="provenance", postgresql_concurrently=True
    )
