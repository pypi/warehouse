# Copyright 2013 Donald Stufft
#
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
Add created column to releases table

Revision ID: 4cdc5a748370
Revises: 77e04097be5
Create Date: 2013-10-24 20:41:22.847711
"""
from __future__ import absolute_import, division, print_function

# revision identifiers, used by Alembic.
revision = "4cdc5a748370"
down_revision = "77e04097be5"

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column(
        "releases",
        sa.Column("created", sa.DateTime(), nullable=True),
    )
    op.alter_column("releases", "created", server_default=sa.func.now())


def downgrade():
    op.drop_column("releases", "created")
