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
add id index to journals

Revision ID: 416778ef37b
Revises: 8f38eea7678
Create Date: 2014-07-20 20:53:09.251525
"""

# revision identifiers, used by Alembic.
revision = '416778ef37b'
down_revision = '8f38eea7678'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.execute(
        "CREATE INDEX journals_id_idx ON journals (id);"
    )


def downgrade():
    op.drop_index("journals_id_idx")
