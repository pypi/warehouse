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
Add file_registry

Revision ID: 28d02f97b58
Revises: 416778ef37b
Create Date: 2015-01-24 11:23:10.370579
"""

# revision identifiers, used by Alembic.
revision = '28d02f97b58'
down_revision = '416778ef37b'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'file_registry',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.UnicodeText(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('filename', name='file_registry_filename_key')
        )


def downgrade():
    op.drop_table('file_registry')
