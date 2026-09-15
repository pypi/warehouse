# SPDX-License-Identifier: Apache-2.0
"""
ultranormalize_name function

Revision ID: d18d443f89f0
Revises: d582fb87b94c
Create Date: 2021-12-17 06:25:19.035417
"""

from alembic import op

revision = "d18d443f89f0"
down_revision = "d582fb87b94c"


def upgrade():
    op.execute(r"""
        CREATE FUNCTION ultranormalize_name(text) RETURNS text AS $$
                SELECT lower(
                    regexp_replace(
                        regexp_replace(
                            regexp_replace($1, '(\.|_|-)', '', 'ig'),
                            '(l|L|i|I)', '1', 'ig'
                        ),
                        '(o|O)', '0', 'ig'
                    )
                )
            $$
            LANGUAGE SQL
            IMMUTABLE
            RETURNS NULL ON NULL INPUT;
    """)
    op.execute(""" CREATE INDEX project_name_ultranormalized
            ON projects
            (ultranormalize_name(name))
        """)


def downgrade():
    op.execute("DROP INDEX project_name_ultranormalized")
    op.execute("DROP FUNCTION ultranormalize_name(text)")
