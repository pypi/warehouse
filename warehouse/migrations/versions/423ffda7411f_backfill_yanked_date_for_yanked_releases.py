# SPDX-License-Identifier: Apache-2.0
"""
Backfill yanked_date for yanked releases

Revision ID: 423ffda7411f
Revises: 3f0c896f7f06
Create Date: 2026-07-20 16:52:19.683225
"""

import sqlalchemy as sa

from alembic import op

revision = "423ffda7411f"
down_revision = "3f0c896f7f06"


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text("SET statement_timeout = 120000"))
    conn.execute(
        sa.text("""
            UPDATE releases
            SET yanked_date = subquery.max_submitted_date
            FROM (
                SELECT
                    projects.id AS project_id,
                    journals.version,
                    MAX(journals.submitted_date) AS max_submitted_date
                FROM journals
                JOIN projects ON projects.name = journals.name
                WHERE journals.action = 'yank release'
                GROUP BY projects.id, journals.version
            ) AS subquery
            WHERE releases.project_id = subquery.project_id
              AND releases.version = subquery.version
              AND releases.yanked = true
              AND releases.yanked_date IS NULL
        """)
    )


def downgrade():
    pass
