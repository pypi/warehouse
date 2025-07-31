# SPDX-License-Identifier: Apache-2.0
"""
Add a function to get the array index

Revision ID: 6a03266b2d
Revises: 3bc5176b880
Create Date: 2015-11-18 18:29:57.554319
"""

from alembic import op

revision = "6a03266b2d"
down_revision = "3bc5176b880"


def upgrade():
    op.execute(
        """ CREATE FUNCTION array_idx(anyarray, anyelement)
            RETURNS INT AS
            $$
                SELECT i FROM (
                    SELECT generate_series(array_lower($1,1),array_upper($1,1))
                ) g(i)
                WHERE $1[i] = $2
                LIMIT 1;
            $$ LANGUAGE SQL IMMUTABLE;
        """
    )


def downgrade():
    op.execute("DROP FUNCTION array_idx")
