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
Add observation_kid to prohibited_project_names

Revision ID: db7633e75422
Revises: 635b80625fc9
Create Date: 2025-03-03 20:21:55.738828
"""

import sqlalchemy as sa

from alembic import op

revision = "db7633e75422"
down_revision = "635b80625fc9"


def upgrade():
    op.add_column(
        "prohibited_project_names",
        sa.Column(
            "observation_kind",
            sa.String(),
            nullable=True,
            comment="If this was created via an observation, the kind of observation",
        ),
    )


def downgrade():
    op.drop_column("prohibited_project_names", "observation_kind")
