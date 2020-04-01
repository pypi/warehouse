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
