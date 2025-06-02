# SPDX-License-Identifier: Apache-2.0
"""
add archived column to files

Revision ID: d142f435bb39
Revises: 665b6f8fd9ac
Create Date: 2023-04-11 10:11:22.602965
"""

import sqlalchemy as sa

from alembic import op

revision = "d142f435bb39"
down_revision = "665b6f8fd9ac"


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text("SET statement_timeout = 120000"))
    op.add_column(
        "release_files",
        sa.Column(
            "archived",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="If True, the object has been archived to our archival bucket.",
        ),
    )

    # CREATE INDEX CONCURRENTLY cannot happen inside a transaction. We'll close
    # our transaction here and issue the statement.
    op.get_bind().commit()
    with op.get_context().autocommit_block():
        op.create_index(
            "release_files_archived_idx",
            "release_files",
            ["archived"],
            unique=False,
            postgresql_concurrently=True,
        )


def downgrade():
    op.drop_index("release_files_archived_idx", table_name="release_files")
    op.drop_column("release_files", "archived")
