# SPDX-License-Identifier: Apache-2.0
"""
Add GIN trigram index on users.username

Revision ID: ff0b39808d7c
Revises: b9d3c5e8f1a2
Create Date: 2026-07-08 22:12:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "ff0b39808d7c"
down_revision = "b9d3c5e8f1a2"


def upgrade():
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction. Commit the
    # migration's transaction and issue the statement in an autocommit block.
    op.get_bind().commit()

    with op.get_context().autocommit_block():
        # env.py sets statement_timeout = 5000; a GIN trigram build over ~1M
        # rows needs more headroom or it is cancelled, leaving an INVALID index.
        op.execute(sa.text("SET statement_timeout = 120000"))  # 120s
        op.execute(sa.text("SET lock_timeout = 5000"))  # 5s

        op.create_index(
            "idx_users_username_trgm",
            "users",
            ["username"],
            unique=False,
            postgresql_using="gin",
            postgresql_ops={"username": "gin_trgm_ops"},
            postgresql_concurrently=True,
        )


def downgrade():
    op.drop_index("idx_users_username_trgm", table_name="users")
