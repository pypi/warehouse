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
remove two_factor_allowed

Revision ID: e1b493d3b171
Revises: 9ca7d5668af4
Create Date: 2019-05-20 20:39:28.616037
"""

import sqlalchemy as sa

from alembic import op

revision = "e1b493d3b171"
down_revision = "9ca7d5668af4"


def upgrade():
    op.drop_column("users", "two_factor_allowed")


def downgrade():
    op.add_column(
        "users",
        sa.Column(
            "two_factor_allowed",
            sa.BOOLEAN(),
            server_default=sa.text("false"),
            autoincrement=False,
            nullable=False,
        ),
    )
