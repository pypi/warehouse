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
create deprecated fields

Revision ID: 63caa2edd396
Revises: 3d2b8a42219a
Create Date: 2016-09-22 10:38:27.188455
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM


revision = '63caa2edd396'
down_revision = '3d2b8a42219a'


def upgrade():
    enum = ENUM("eol", "insecure", name="deprecated_type", create_type=False)
    enum.create(op.get_bind(), checkfirst=False)
    op.add_column(
        'releases',
        sa.Column('deprecated_at', sa.DateTime(), nullable=True)
    )
    op.add_column(
        'releases',
        sa.Column(
            'deprecated_reason',
            sa.Enum('eol', 'insecure', name='deprecated_type'),
            nullable=True
        )
    )
    op.add_column(
        'releases',
        sa.Column('deprecated_url', sa.Text(), nullable=True)
    )


def downgrade():
    op.drop_column('releases', 'deprecated_url')
    op.drop_column('releases', 'deprecated_reason')
    op.drop_column('releases', 'deprecated_at')
