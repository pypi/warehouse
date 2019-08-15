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
key events on username and project name

Revision ID: 3708ffc77ab5
Revises: 0ac2f506ef2e
Create Date: 2019-08-15 22:33:30.297279
"""

import citext
import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "3708ffc77ab5"
down_revision = "0ac2f506ef2e"


def upgrade():
    op.add_column(
        "project_events", sa.Column("project_name", sa.Text(), nullable=False)
    )
    op.drop_constraint(
        "project_events_project_id_fkey", "project_events", type_="foreignkey"
    )
    op.create_foreign_key(
        None,
        "project_events",
        "projects",
        ["project_name"],
        ["name"],
        initially="DEFERRED",
        deferrable=True,
    )
    op.drop_column("project_events", "project_id")
    op.add_column(
        "user_events", sa.Column("user_username", citext.CIText(), nullable=False)
    )
    op.drop_constraint("user_events_user_id_fkey", "user_events", type_="foreignkey")
    op.create_foreign_key(
        None,
        "user_events",
        "users",
        ["user_username"],
        ["username"],
        initially="DEFERRED",
        deferrable=True,
    )
    op.drop_column("user_events", "user_id")


def downgrade():
    op.add_column(
        "user_events",
        sa.Column("user_id", postgresql.UUID(), autoincrement=False, nullable=False),
    )
    op.drop_constraint(None, "user_events", type_="foreignkey")
    op.create_foreign_key(
        "user_events_user_id_fkey",
        "user_events",
        "users",
        ["user_id"],
        ["id"],
        initially="DEFERRED",
        deferrable=True,
    )
    op.drop_column("user_events", "user_username")
    op.add_column(
        "project_events",
        sa.Column("project_id", postgresql.UUID(), autoincrement=False, nullable=False),
    )
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
    op.drop_column("project_events", "project_name")
