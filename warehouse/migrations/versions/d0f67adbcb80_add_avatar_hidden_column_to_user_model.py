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
Add 'avatar_hidden' column to User model

Revision ID: d0f67adbcb80
Revises: fe2e3d22b3fa
Create Date: 2022-09-28 16:02:44.054680
"""

import sqlalchemy as sa

from alembic import op

revision = "d0f67adbcb80"
down_revision = "fe2e3d22b3fa"


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "hide_avatar", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )


def downgrade():
    op.drop_column("users", "hide_avatar")
