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
Remove MissingDatasetFile

Revision ID: 2a2c32c47a8f
Revises: 77d52a945a5f
Create Date: 2025-01-21 15:49:29.129691
"""

import sqlalchemy as sa

from alembic import op

revision = "2a2c32c47a8f"
down_revision = "77d52a945a5f"


def upgrade():
    op.drop_table("missing_dataset_files")


def downgrade():
    op.create_table(
        "missing_dataset_files",
        sa.Column("file_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("processed", sa.BOOLEAN(), autoincrement=False, nullable=True),
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["release_files.id"], name="missing_dataset_files_file_id_fkey"
        ),
        sa.PrimaryKeyConstraint("id", name="missing_dataset_files_pkey"),
    )
