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
add last totp value to user

Revision ID: 34b18e18775c
Revises: 0ac2f506ef2e
Create Date: 2019-08-15 21:28:47.621282
"""

import sqlalchemy as sa

from alembic import op

revision = "34b18e18775c"
down_revision = "0ac2f506ef2e"


def upgrade():
    op.add_column("users", sa.Column("last_totp_value", sa.String(), nullable=True))


def downgrade():
    op.drop_column("users", "last_totp_value")
