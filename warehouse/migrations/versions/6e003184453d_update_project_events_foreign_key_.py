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
Update project_events foreign key constraint

Revision ID: 6e003184453d
Revises: 9f0f99509d92
Create Date: 2022-04-25 21:49:27.917725
"""

from alembic import op

revision = "6e003184453d"
down_revision = "bb986a64761a"


def upgrade():
    op.drop_constraint(
        "project_events_project_id_fkey", "project_events", type_="foreignkey"
    )
    op.create_foreign_key(
        None,
        "project_events",
        "projects",
        ["source_id"],
        ["id"],
        initially="DEFERRED",
        deferrable=True,
    )


def downgrade():
    op.drop_constraint(None, "project_events", type_="foreignkey")
    op.create_foreign_key(
        "project_events_project_id_fkey",
        "project_events",
        "projects",
        ["source_id"],
        ["id"],
        ondelete="CASCADE",
        initially="DEFERRED",
        deferrable=True,
    )
