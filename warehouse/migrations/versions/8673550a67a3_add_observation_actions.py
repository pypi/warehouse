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
Add Observation.actions

Revision ID: 8673550a67a3
Revises: 73c201ff90f3
Create Date: 2024-04-11 20:45:05.218380
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "8673550a67a3"
down_revision = "73c201ff90f3"


def upgrade():
    op.add_column(
        "project_observations",
        sa.Column(
            "actions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
            comment="Actions taken based on the observation",
        ),
    )
    op.add_column(
        "release_observations",
        sa.Column(
            "actions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
            comment="Actions taken based on the observation",
        ),
    )


def downgrade():
    op.drop_column("release_observations", "actions")
    op.drop_column("project_observations", "actions")
