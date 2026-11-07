# SPDX-License-Identifier: Apache-2.0
"""
Add GIN trigram index on ultranormalize_name(projects.name)

Revision ID: 5b1c8e7f2a9d
Revises: e7c1c116be9a
Create Date: 2026-10-28 10:30:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "5b1c8e7f2a9d"
down_revision = "e7c1c116be9a"


def upgrade():
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction. Commit the
    # migration's transaction and issue the statement in an autocommit block.
    op.get_bind().commit()

    with op.get_context().autocommit_block():
        # env.py sets statement_timeout = 5000; a cancelled build leaves an
        # INVALID index that blocks the retry. Normalizing every name alone
        # takes ~2s in production, and the GIN build sits on top of that.
        op.execute(sa.text("SET statement_timeout = 300000"))  # 300s
        op.execute(sa.text("SET lock_timeout = 5000"))  # 5s

        # Raw SQL: op.create_index() attaches the operator class by expression
        # key, which a text() expression lacks, so it would silently be dropped.
        op.execute(
            sa.text(
                "CREATE INDEX CONCURRENTLY projects_name_ultranormalized_trgm "
                "ON projects USING gin (ultranormalize_name(name) gin_trgm_ops)"
            )
        )


def downgrade():
    op.drop_index("projects_name_ultranormalized_trgm", table_name="projects")
