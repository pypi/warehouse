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
Add field on User model for is_moderator

Revision ID: 3db69c05dd11
Revises: 67f52a64a389
Create Date: 2019-01-04 21:29:45.455607
"""

import sqlalchemy as sa

from alembic import op

revision = "3db69c05dd11"
down_revision = "67f52a64a389"


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "is_moderator", sa.Boolean(), nullable=False, server_default=sa.sql.false()
        ),
    )


def downgrade():
    op.drop_column("users", "is_moderator")
