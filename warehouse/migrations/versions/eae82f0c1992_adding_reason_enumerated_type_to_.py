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
adding reason enumerated type to database

Revision ID: eae82f0c1992
Revises: e82c3a017d60
Create Date: 2018-10-27 16:19:29.089625
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'eae82f0c1992'
down_revision = 'e82c3a017d60'

# Note: It is VERY important to ensure that a migration does not lock for a
#       long period of time and to ensure that each individual migration does
#       not break compatibility with the *previous* version of the code base.
#       This is because the migrations will be ran automatically as part of the
#       deployment process, but while the previous version of the code is still
#       up and running. Thus backwards incompatible changes must be broken up
#       over multiple migrations inside of multiple pull requests in order to
#       phase them in over multiple deploys.

def upgrade():
    black_list_reason = postgresql.ENUM('other', 'not_labeled', 'spam', 'malicious', 'typo_squat', 'dmca',
                                        name='blacklistreason')
    black_list_reason.create(op.get_bind())
    reason_enum = sa.Enum('other', 'not_labeled', 'spam', 'malicious', 'typo_squat', 'dmca', name='blacklistreason')
    op.add_column('blacklist', sa.Column('reason', reason_enum, nullable=True, server_default="not_labeled"))
    op.alter_column('blacklist', 'reason', server_default=None)

def downgrade():
    op.drop_column('blacklist', 'reason')
    op.execute("DROP TYPE blacklistreason;")
