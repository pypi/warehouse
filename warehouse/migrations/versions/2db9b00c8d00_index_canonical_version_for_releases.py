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
index canonical_version for releases

Revision ID: 2db9b00c8d00
Revises: 8a335305fd39
Create Date: 2022-07-22 16:54:20.701648
"""

from alembic import op

revision = "2db9b00c8d00"
down_revision = "8a335305fd39"


def upgrade():
    # CREATE INDEX CONCURRENTLY cannot happen inside a transaction. We'll close
    # our transaction here and issue the statement.
    op.get_bind().commit()

    with op.get_context().autocommit_block():
        op.create_index(
            "release_canonical_version_idx",
            "releases",
            ["canonical_version"],
            unique=False,
            postgresql_concurrently=True,
        )


def downgrade():
    op.drop_index("release_canonical_version_idx", table_name="releases")
