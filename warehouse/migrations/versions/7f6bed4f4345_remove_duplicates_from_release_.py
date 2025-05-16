# SPDX-License-Identifier: Apache-2.0
"""
Remove duplicates from release_classifiers

Revision ID: 7f6bed4f4345
Revises: a8ebe73ccaf2
Create Date: 2023-08-16 22:56:54.898269
"""

from alembic import op

revision = "7f6bed4f4345"
down_revision = "a8ebe73ccaf2"


def upgrade():
    op.execute("SET statement_timeout = 60000")  # 60s
    op.execute("SET lock_timeout = 60000")  # 60s

    op.execute(
        """
        DELETE FROM release_classifiers a USING (
            SELECT MIN(ctid) as ctid, release_id, trove_id
            FROM release_classifiers
            GROUP BY release_id, trove_id HAVING COUNT(*) > 1
            LIMIT 4453 -- 4453 is the number of duplicates in production
        ) b
        WHERE a.release_id = b.release_id
        AND a.trove_id = b.trove_id
        AND a.ctid <> b.ctid;
        """
    )


def downgrade():
    # No going back.
    pass
