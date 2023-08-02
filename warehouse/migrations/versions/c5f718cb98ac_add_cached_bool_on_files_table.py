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
add cached bool on files table

Revision ID: c5f718cb98ac
Revises: 6073f65a2767
Create Date: 2023-05-12 08:00:47.726442
"""

import sqlalchemy as sa

from alembic import op

revision = "c5f718cb98ac"
down_revision = "6073f65a2767"


def upgrade():
    op.add_column(
        "release_files",
        sa.Column(
            "cached",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="If True, the object has been populated to our cache bucket.",
        ),
    )
    # CREATE INDEX CONCURRENTLY cannot happen inside a transaction. We'll close
    # our transaction here and issue the statement.
    op.get_bind().commit()
    with op.get_context().autocommit_block():
        op.create_index(
            "release_files_cached_idx",
            "release_files",
            ["cached"],
            unique=False,
            postgresql_concurrently=True,
        )


def downgrade():
    op.drop_index("release_files_cached_idx", table_name="release_files")
    op.drop_column("release_files", "cached")
