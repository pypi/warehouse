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
add archived column to files

Revision ID: d142f435bb39
Revises: 665b6f8fd9ac
Create Date: 2023-04-11 10:11:22.602965
"""

import sqlalchemy as sa

from alembic import op

revision = "d142f435bb39"
down_revision = "665b6f8fd9ac"


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text("SET statement_timeout = 120000"))
    op.add_column(
        "release_files",
        sa.Column(
            "archived",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="If True, the object has been archived to our archival bucket.",
        ),
    )

    # CREATE INDEX CONCURRENTLY cannot happen inside a transaction. We'll close
    # our transaction here and issue the statement.
    op.get_bind().commit()
    with op.get_context().autocommit_block():
        op.create_index(
            "release_files_archived_idx",
            "release_files",
            ["archived"],
            unique=False,
            postgresql_concurrently=True,
        )


def downgrade():
    op.drop_index("release_files_archived_idx", table_name="release_files")
    op.drop_column("release_files", "archived")
