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
redistribute sitemap buckets

Revision ID: c4cb2d15dada
Revises: d15f020ee3df
Create Date: 2020-04-07 16:59:56.333491
"""

from alembic import op

revision = "c4cb2d15dada"
down_revision = "d15f020ee3df"


def upgrade():
    op.execute(
        """
        CREATE OR REPLACE FUNCTION sitemap_bucket(text) RETURNS text AS $$
                SELECT substring(
                    encode(digest($1, 'sha512'), 'hex')
                    from 1
                    for 2
                )
            $$
            LANGUAGE SQL
            IMMUTABLE
            RETURNS NULL ON NULL INPUT;
    """
    )
    op.execute(
        """
        UPDATE users
        SET sitemap_bucket = sitemap_bucket(username)
        """
    )
    op.execute(
        """
        UPDATE projects
        SET sitemap_bucket = sitemap_bucket(name)
        """
    )


def downgrade():
    op.execute(
        """
        CREATE OR REPLACE FUNCTION sitemap_bucket(text) RETURNS text AS $$
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
    op.execute(
        """
        UPDATE users
        SET sitemap_bucket = sitemap_bucket(username)
        """
    )
    op.execute(
        """
        UPDATE projects
        SET sitemap_bucket = sitemap_bucket(name)
        """
    )
