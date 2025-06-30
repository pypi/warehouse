# SPDX-License-Identifier: Apache-2.0
"""
redistribute sitemap buckets

Revision ID: c4cb2d15dada
Revises: d15f020ee3df
Create Date: 2020-04-07 16:59:56.333491
"""

from alembic import op

revision = "c4cb2d15dada"
down_revision = "d15f020ee3df"


def upgrade():
    op.execute(
        """
        CREATE OR REPLACE FUNCTION sitemap_bucket(text) RETURNS text AS $$
                SELECT substring(
                    encode(digest($1, 'sha512'), 'hex')
                    from 1
                    for 2
                )
            $$
            LANGUAGE SQL
            IMMUTABLE
            RETURNS NULL ON NULL INPUT;
    """
    )
    op.execute(
        """
        UPDATE users
        SET sitemap_bucket = sitemap_bucket(username)
        """
    )
    op.execute(
        """
        UPDATE projects
        SET sitemap_bucket = sitemap_bucket(name)
        """
    )


def downgrade():
    op.execute(
        """
        CREATE OR REPLACE FUNCTION sitemap_bucket(text) RETURNS text AS $$
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
    op.execute(
        """
        UPDATE users
        SET sitemap_bucket = sitemap_bucket(username)
        """
    )
    op.execute(
        """
        UPDATE projects
        SET sitemap_bucket = sitemap_bucket(name)
        """
    )
