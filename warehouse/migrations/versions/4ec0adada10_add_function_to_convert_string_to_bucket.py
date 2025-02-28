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
Add function to convert string to bucket

Revision ID: 4ec0adada10
Revises: 9177113533
Create Date: 2015-09-06 19:32:50.438462
"""

from alembic import op

revision = "4ec0adada10"
down_revision = "9177113533"


def upgrade():
    op.execute(
        """
        CREATE FUNCTION sitemap_bucket(text) RETURNS text AS $$
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


def downgrade():
    op.execute("DROP FUNCTION sitemap_bucket(text)")
