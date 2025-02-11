# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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
