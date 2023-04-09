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
add archived column to files table

Revision ID: 360dc6a7eb7a
Revises: 203f1f8dcf92
Create Date: 2023-04-09 15:03:39.717818
"""

import sqlalchemy as sa

from alembic import op

revision = "360dc6a7eb7a"
down_revision = "203f1f8dcf92"


def upgrade():
    op.add_column(
        "release_files",
        sa.Column(
            "archived", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.create_index(
        "release_files_archived_idx", "release_files", ["archived"], unique=False
    )


def downgrade():
    op.drop_index("release_files_archived_idx", table_name="release_files")
    op.drop_column("release_files", "archived")
