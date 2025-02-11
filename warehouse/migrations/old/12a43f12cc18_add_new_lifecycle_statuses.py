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
Add new lifecycle statuses

Revision ID: 12a43f12cc18
Revises: 24aa37164e72
"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "12a43f12cc18"
down_revision = "24aa37164e72"


def upgrade():
    op.execute("ALTER TYPE public.lifecyclestatus ADD VALUE IF NOT EXISTS 'archived'")


def downgrade():
    op.sync_enum_values(
        "public",
        "lifecyclestatus",
        ["quarantine-enter", "quarantine-exit"],
        [
            TableReference(
                table_schema="public",
                table_name="projects",
                column_name="lifecycle_status",
            )
        ],
        enum_values_to_rename=[],
    )
