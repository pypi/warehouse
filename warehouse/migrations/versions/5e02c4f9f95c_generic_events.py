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
Generic Events

Revision ID: 5e02c4f9f95c
Revises: 87509f4ae027
Create Date: 2020-07-26 06:12:58.519387
"""


from alembic import op

revision = "5e02c4f9f95c"
down_revision = "84262e097c26"


def upgrade():
    op.alter_column("project_events", "project_id", new_column_name="source_id")
    op.execute(
        "ALTER INDEX ix_project_events_project_id RENAME TO ix_project_events_source_id"  # noqa
    )

    op.alter_column("user_events", "user_id", new_column_name="source_id")
    op.execute("ALTER INDEX ix_user_events_user_id RENAME TO ix_user_events_source_id")


def downgrade():
    op.alter_column("project_events", "source_id", new_column_name="project_id")
    op.execute(
        "ALTER INDEX ix_project_events_source_id RENAME TO ix_project_events_project_id"  # noqa
    )

    op.alter_column("user_events", "source_id", new_column_name="user_id")
    op.execute("ALTER INDEX ix_user_events_source_id RENAME TO ix_user_events_user_id")
