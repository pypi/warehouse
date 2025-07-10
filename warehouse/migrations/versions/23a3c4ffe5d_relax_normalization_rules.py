# SPDX-License-Identifier: Apache-2.0
"""
relax normalization rules

Revision ID: 23a3c4ffe5d
Revises: 91508cc5c2
Create Date: 2015-06-04 22:44:16.490470
"""

from alembic import op

revision = "23a3c4ffe5d"
down_revision = "91508cc5c2"


def upgrade():
    op.execute("DROP INDEX project_name_pep426_normalized")

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


def downgrade():
    op.execute(
        r""" CREATE OR REPLACE FUNCTION normalize_pep426_name(text)
            RETURNS text AS
            $$
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

    op.execute(
        """ CREATE UNIQUE INDEX project_name_pep426_normalized
            ON packages
            (normalize_pep426_name(name))
        """
    )
