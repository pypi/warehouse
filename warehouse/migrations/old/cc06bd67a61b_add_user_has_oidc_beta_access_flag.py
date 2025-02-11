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
Add User.has_oidc_beta_access flag

Revision ID: cc06bd67a61b
Revises: 0cb51a600b59
Create Date: 2023-02-23 18:52:59.525595
"""

import sqlalchemy as sa

from alembic import op

revision = "cc06bd67a61b"
down_revision = "0cb51a600b59"


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "has_oidc_beta_access",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("users", "has_oidc_beta_access")
