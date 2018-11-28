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
Add a column to project to record the zscore

Revision ID: 5b3f9e687d94
Revises: 7750037b351a
Create Date: 2017-03-10 02:14:12.402080
"""

import sqlalchemy as sa

from alembic import op

revision = "5b3f9e687d94"
down_revision = "7750037b351a"


def upgrade():
    op.add_column("packages", sa.Column("zscore", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("packages", "zscore")
