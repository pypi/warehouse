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
Cascade project_events deletion

Revision ID: 69b928240b2f
Revises: 99a201142761
Create Date: 2021-02-08 21:45:22.759363
"""

from alembic import op

revision = "69b928240b2f"
down_revision = "99a201142761"


def upgrade():
    op.drop_constraint(
        "project_events_project_id_fkey", "project_events", type_="foreignkey"
    )
    op.create_foreign_key(
        None,
        "project_events",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
        initially="DEFERRED",
        deferrable=True,
    )


def downgrade():
    op.drop_constraint(None, "project_events", type_="foreignkey")
    op.create_foreign_key(
        "project_events_project_id_fkey",
        "project_events",
        "projects",
        ["project_id"],
        ["id"],
        initially="DEFERRED",
        deferrable=True,
    )
