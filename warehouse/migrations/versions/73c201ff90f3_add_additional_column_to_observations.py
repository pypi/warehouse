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
Add additional column to Observations

Revision ID: 73c201ff90f3
Revises: 34c3175f4bea
Create Date: 2024-04-11 18:22:08.928952
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "73c201ff90f3"
down_revision = "34c3175f4bea"


def upgrade():
    op.add_column(
        "project_observations",
        sa.Column(
            "additional",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
            comment="Additional data for the observation",
        ),
    )
    op.add_column(
        "release_observations",
        sa.Column(
            "additional",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
            comment="Additional data for the observation",
        ),
    )


def downgrade():
    op.drop_column("release_observations", "additional")
    op.drop_column("project_observations", "additional")
