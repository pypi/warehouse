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
Remove array_idx

Revision ID: 02ee200cb3ac
Revises: b27b3bb5b4c9
Create Date: 2025-02-24 20:50:14.944982
"""

from alembic import op

revision = "02ee200cb3ac"
down_revision = "b27b3bb5b4c9"


def upgrade():
    op.execute("DROP FUNCTION array_idx")


def downgrade():
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
