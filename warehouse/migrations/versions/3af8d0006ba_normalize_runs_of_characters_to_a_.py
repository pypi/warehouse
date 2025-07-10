# SPDX-License-Identifier: Apache-2.0
"""
Normalize runs of characters to a single character

Revision ID: 3af8d0006ba
Revises: 5ff0c99c94
Create Date: 2015-08-17 21:05:51.699639
"""

from alembic import op

revision = "3af8d0006ba"
down_revision = "5ff0c99c94"


def upgrade():
    op.execute(
        r""" CREATE OR REPLACE FUNCTION normalize_pep426_name(text)
            RETURNS text AS
            $$
                SELECT lower(regexp_replace($1, '(\.|_|-)+', '-', 'ig'))
            $$
            LANGUAGE SQL
            IMMUTABLE
            RETURNS NULL ON NULL INPUT;
        """
    )
    op.execute("REINDEX INDEX project_name_pep426_normalized")


def downgrade():
    op.execute(
        r""" CREATE OR REPLACE FUNCTION normalize_pep426_name(text)
            RETURNS text AS
            $$
                SELECT lower(regexp_replace($1, '(\.|_)', '-', 'ig'))
            $$
            LANGUAGE SQL
            IMMUTABLE
            RETURNS NULL ON NULL INPUT;
        """
    )
    op.execute("REINDEX INDEX project_name_pep426_normalized")
