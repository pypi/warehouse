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
