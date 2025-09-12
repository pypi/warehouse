# SPDX-License-Identifier: Apache-2.0
"""
Create a Normalize Function for PEP 426 names.

Revision ID: 20f4dbe11e9
Revises: 111d8fc0443
Create Date: 2015-04-04 23:29:58.373217
"""

from alembic import op

revision = "20f4dbe11e9"
down_revision = "111d8fc0443"


def upgrade():
    op.execute(
        r"""
        CREATE FUNCTION normalize_pep426_name(text) RETURNS text AS $$
                SELECT lower(
                    regexp_replace(
                        regexp_replace(
                            regexp_replace($1, '(\.|_)', '-', 'ig'),
                            '(1|l|I)', '1', 'ig'
                        ),
                        '(0|0)', '0', 'ig'
                    )
                )
            $$
            LANGUAGE SQL
            IMMUTABLE
            RETURNS NULL ON NULL INPUT;
    """
    )


def downgrade():
    op.execute("DROP FUNCTION normalize_pep426_name(text)")
