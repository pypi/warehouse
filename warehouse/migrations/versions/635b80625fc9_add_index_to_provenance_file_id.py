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
Add index to Provenance.file_id

Revision ID: 635b80625fc9
Revises: 2f5dbc74c770
Create Date: 2025-02-28 17:41:58.763011
"""

from alembic import op

revision = "635b80625fc9"
down_revision = "2f5dbc74c770"


def upgrade():
    # CREATE INDEX CONCURRENTLY cannot happen inside a transaction. We'll close
    # our transaction here and issue the statement.
    op.get_bind().commit()
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_provenance_file_id",
            "provenance",
            ["file_id"],
            unique=False,
            postgresql_concurrently=True,
        )


def downgrade():
    op.drop_index(
        "ix_provenance_file_id", table_name="provenance", postgresql_concurrently=True
    )
