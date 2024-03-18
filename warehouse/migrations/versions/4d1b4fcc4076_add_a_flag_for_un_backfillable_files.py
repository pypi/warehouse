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
Add a flag for un-backfillable files

Revision ID: 4d1b4fcc4076
Revises: be62a4cd76e3
Create Date: 2024-02-13 23:15:18.105618
"""

import sqlalchemy as sa

from alembic import op

revision = "4d1b4fcc4076"
down_revision = "be62a4cd76e3"


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text("SET statement_timeout = 120000"))

    op.add_column(
        "release_files",
        sa.Column(
            "metadata_file_unbackfillable",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=True,
            comment="If True, the metadata for the file cannot be backfilled.",
        ),
    )


def downgrade():
    op.drop_column("release_files", "metadata_file_unbackfillable")
