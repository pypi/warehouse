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
remove two_factor_prohibited

Revision ID: 460a9c1b9890
Revises: e1b493d3b171
Create Date: 2019-05-30 04:35:24.470935
"""

import sqlalchemy as sa

from alembic import op

revision = "460a9c1b9890"
down_revision = "e1b493d3b171"


def upgrade():
    op.drop_column("users", "two_factor_prohibited")


def downgrade():
    op.add_column(
        "users",
        sa.Column(
            "two_factor_prohibited",
            sa.BOOLEAN(),
            server_default=sa.text("false"),
            autoincrement=False,
            nullable=False,
        ),
    )
