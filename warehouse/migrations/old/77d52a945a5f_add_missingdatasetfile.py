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
Add MissingDatasetFile

Revision ID: 77d52a945a5f
Revises: 12a43f12cc18
Create Date: 2025-01-17 16:56:09.082853
"""

import sqlalchemy as sa

from alembic import op

revision = "77d52a945a5f"
down_revision = "12a43f12cc18"


def upgrade():
    op.create_table(
        "missing_dataset_files",
        sa.Column("file_id", sa.UUID(), nullable=False),
        sa.Column("processed", sa.Boolean(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["release_files.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("missing_dataset_files")
