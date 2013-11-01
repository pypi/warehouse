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
Add an index on (releases.name, releases.created)

Revision ID: 23515b7500af
Revises: 3175e1bdb1b5
Create Date: 2013-10-31 10:51:16.152183
"""
from __future__ import absolute_import, division, print_function

# revision identifiers, used by Alembic.
revision = '23515b7500af'
down_revision = '3175e1bdb1b5'

from alembic import op


def upgrade():
    op.execute(
        "CREATE INDEX release_name_created_idx ON releases(name, created DESC)"
    )


def downgrade():
    op.drop_index("release_name_created_idx")
