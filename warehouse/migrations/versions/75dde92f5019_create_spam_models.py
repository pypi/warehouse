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
create spam models

Revision ID: 75dde92f5019
Revises: b75709859292
Create Date: 2018-02-19 20:16:00.579309
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '75dde92f5019'
down_revision = 'b75709859292'


def upgrade():
    op.create_table(
        'spam_report',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False
        ),
        sa.Column('release_name', sa.Text(), nullable=False),
        sa.Column('release_version', sa.Text(), nullable=False),
        sa.Column(
            'source',
            postgresql.ENUM(
                'automation', 'user',
                name='report_source_enum'
            ),
            nullable=False
        ),
        sa.Column('reporter_user_id', postgresql.UUID(), nullable=True),
        sa.Column('result', sa.Boolean(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('valid', sa.Boolean(), nullable=True),
        sa.CheckConstraint(
            "reporter_user_id IS NOT NULL OR source = 'automation'",
            name='valid_reporter_user_id'
        ),
        sa.ForeignKeyConstraint(
            ['release_name', 'release_version'],
            ['releases.name', 'releases.version'],
            onupdate='CASCADE', ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('spam_report')
