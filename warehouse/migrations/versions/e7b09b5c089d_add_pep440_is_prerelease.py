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
Add pep440_is_prerelease

Revision ID: e7b09b5c089d
Revises: be4cf6b58557
Create Date: 2016-12-03 15:04:40.251609
"""

from alembic import op

revision = "e7b09b5c089d"
down_revision = "be4cf6b58557"


def upgrade():
    op.execute(
        """
        CREATE FUNCTION pep440_is_prerelease(text) returns boolean as $$
                SELECT lower($1) ~* '(a|b|rc|dev|alpha|beta|c|pre|preview)'
            $$
            LANGUAGE SQL
            IMMUTABLE
            RETURNS NULL ON NULL INPUT;
    """
    )


def downgrade():
    op.execute("DROP FUNCTION pep440_is_prerelease")
