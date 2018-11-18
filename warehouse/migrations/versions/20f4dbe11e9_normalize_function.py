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
