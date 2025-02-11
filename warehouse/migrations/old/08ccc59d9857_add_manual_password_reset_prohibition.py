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
add manual password reset prohibition

Revision ID: 08ccc59d9857
Revises: 10825786b3df
Create Date: 2021-07-13 14:40:16.604041
"""

import sqlalchemy as sa

from alembic import op

revision = "08ccc59d9857"
down_revision = "10825786b3df"


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "prohibit_password_reset",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("users", "prohibit_password_reset")
