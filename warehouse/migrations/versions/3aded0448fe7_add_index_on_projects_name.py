# SPDX-License-Identifier: Apache-2.0
"""
Add index on projects.name

Revision ID: 3aded0448fe7
Revises: 5b1c8e7f2a9d
Create Date: 2026-11-19 13:49:38.964874
"""

import sqlalchemy as sa

from alembic import op

revision = "3aded0448fe7"
down_revision = "5b1c8e7f2a9d"


def upgrade():
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction. Commit the
    # migration's transaction and issue the statement in an autocommit block.
    op.get_bind().commit()

    with op.get_context().autocommit_block():
        # env.py sets statement_timeout = 5000, too short for a ~1M row build.
        op.execute(sa.text("SET statement_timeout = 300000"))  # 300s
        op.execute(sa.text("SET lock_timeout = 5000"))  # 5s

        # A cancelled earlier attempt leaves an INVALID index behind; drop it so
        # a retry rebuilds rather than failing on the existing name.
        op.execute(sa.text("DROP INDEX CONCURRENTLY IF EXISTS projects_name_idx"))

        op.create_index(
            "projects_name_idx",
            "projects",
            ["name"],
            unique=False,
            postgresql_concurrently=True,
        )


def downgrade():
    op.drop_index("projects_name_idx", table_name="projects")
