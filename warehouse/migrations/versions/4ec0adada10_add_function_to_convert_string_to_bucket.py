# SPDX-License-Identifier: Apache-2.0
"""
Add function to convert string to bucket

Revision ID: 4ec0adada10
Revises: 9177113533
Create Date: 2015-09-06 19:32:50.438462
"""

from alembic import op

revision = "4ec0adada10"
down_revision = "9177113533"


def upgrade():
    op.execute(
        """
        CREATE FUNCTION sitemap_bucket(text) RETURNS text AS $$
                SELECT substring(
                    encode(digest($1, 'sha512'), 'hex')
                    from 1
                    for 1
                )
            $$
            LANGUAGE SQL
            IMMUTABLE
            RETURNS NULL ON NULL INPUT;
    """
    )


def downgrade():
    op.execute("DROP FUNCTION sitemap_bucket(text)")
