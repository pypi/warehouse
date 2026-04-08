# SPDX-License-Identifier: Apache-2.0
"""
Migrate Existing Data for Release.is_prerelease

Revision ID: 4490777c984f
Revises: b0dbcd2f5c77
Create Date: 2022-06-27 17:49:09.835384
"""

import sqlalchemy as sa

from alembic import op

revision = "4490777c984f"
down_revision = "b0dbcd2f5c77"


def _get_num_rows(conn):
    return list(
        conn.execute(
            sa.text("SELECT COUNT(id) FROM releases WHERE is_prerelease IS NULL")
        )
    )[0][0]


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text("SET statement_timeout = 120000"))
    total_rows = _get_num_rows(conn)
    max_loops = total_rows / 100000 * 2
    loops = 0
    while _get_num_rows(conn) > 0 and loops < max_loops:
        loops += 1
        conn.execute(sa.text("""
                UPDATE releases
                SET is_prerelease = pep440_is_prerelease(version)
                WHERE id IN (
                    SELECT id
                    FROM releases
                    WHERE is_prerelease IS NULL
                    LIMIT 100000
                )
                """))
        op.get_bind().commit()

    op.alter_column(
        "releases",
        "is_prerelease",
        existing_type=sa.BOOLEAN(),
        server_default=sa.text("false"),
        nullable=False,
    )


def downgrade():
    op.alter_column(
        "releases",
        "is_prerelease",
        existing_type=sa.BOOLEAN(),
        server_default=None,
        nullable=True,
    )
