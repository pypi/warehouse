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
Add Project Lifecycle Status

Revision ID: 14ad61e054cf
Revises: b14df478c48f
Create Date: 2024-06-26 20:30:52.083447
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "14ad61e054cf"
down_revision = "b14df478c48f"


def upgrade():
    op.execute("SET statement_timeout = 11000")
    op.execute("SET lock_timeout = 10000")

    sa.Enum("quarantine-enter", "quarantine-exit", name="lifecyclestatus").create(
        op.get_bind()
    )
    op.add_column(
        "projects",
        sa.Column(
            "lifecycle_status",
            postgresql.ENUM(
                "quarantine-enter",
                "quarantine-exit",
                name="lifecyclestatus",
                create_type=False,
            ),
            nullable=True,
            comment="Lifecycle status can change project visibility and access",
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "lifecycle_status_changed",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=True,
            comment="When the lifecycle status was last changed",
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "lifecycle_status_note",
            sa.String(),
            nullable=True,
            comment="Note about the lifecycle status",
        ),
    )
    op.create_index(
        "projects_lifecycle_status_idx", "projects", ["lifecycle_status"], unique=False
    )


def downgrade():
    op.drop_index("projects_lifecycle_status_idx", table_name="projects")
    op.drop_column("projects", "lifecycle_status_note")
    op.drop_column("projects", "lifecycle_status_changed")
    op.drop_column("projects", "lifecycle_status")
    sa.Enum("quarantine-enter", "quarantine-exit", name="lifecyclestatus").drop(
        op.get_bind()
    )
