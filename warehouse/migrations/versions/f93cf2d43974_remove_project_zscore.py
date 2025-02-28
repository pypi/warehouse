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
Remove Project.zscore

Revision ID: f93cf2d43974
Revises: 62601ddf674c
Create Date: 2023-01-24 20:41:03.489453
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f93cf2d43974"
down_revision = "62601ddf674c"


def upgrade():
    op.drop_column("projects", "zscore")


def downgrade():
    op.add_column(
        "projects",
        sa.Column(
            "zscore",
            postgresql.DOUBLE_PRECISION(precision=53),
            autoincrement=False,
            nullable=True,
        ),
    )
