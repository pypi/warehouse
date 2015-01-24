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
Update file_registry

Revision ID: 72ba446c06
Revises: 28d02f97b58
Create Date: 2015-01-24 12:07:34.189955
"""

# revision identifiers, used by Alembic.
revision = '72ba446c06'
down_revision = '28d02f97b58'

from alembic import op


def upgrade():
    op.execute("""
        INSERT INTO file_registry (filename)
        SELECT filename
        FROM release_files
        WHERE filename NOT IN (
            SELECT filename from file_registry
        )
    """)


def downgrade():
    pass
