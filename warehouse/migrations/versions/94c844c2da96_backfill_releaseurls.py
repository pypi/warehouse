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
Backfill ReleaseURLs

Revision ID: 94c844c2da96
Revises: 7a8c380cefa4
Create Date: 2022-06-10 23:54:30.955026
"""

from alembic import op

revision = "94c844c2da96"
down_revision = "7a8c380cefa4"


def upgrade():
    op.create_check_constraint(
        "release_urls_valid_name", "release_urls", "char_length(name) BETWEEN 1 AND 32"
    )
    op.execute(
        r"""
        INSERT INTO release_urls (release_id, name, url)
            SELECT release_id,
                (regexp_match(specifier, '^([^,]+)\s*,\s*(.*)$'))[1],
                (regexp_match(specifier, '^([^,]+)\s*,\s*(.*)$'))[2]
            FROM release_dependencies
            WHERE release_dependencies.kind = 8
            ON CONFLICT ON CONSTRAINT release_urls_release_id_name_key
            DO NOTHING;
        """
    )


def downgrade():
    pass
