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
Remove User.has_oidc_beta_access column

Revision ID: d1771b942eb6
Revises: 75ba94852cd1
Create Date: 2023-04-20 17:33:44.571959
"""

import sqlalchemy as sa

from alembic import op

revision = "d1771b942eb6"
down_revision = "75ba94852cd1"


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text("SET statement_timeout = 120000"))
    conn.execute(sa.text("SET lock_timeout = 120000"))
    op.drop_column("users", "has_oidc_beta_access")


def downgrade():
    op.add_column(
        "users",
        sa.Column(
            "has_oidc_beta_access",
            sa.BOOLEAN(),
            server_default=sa.text("false"),
            autoincrement=False,
            nullable=False,
        ),
    )
