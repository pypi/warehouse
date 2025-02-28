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
Add User.is_frozen

Revision ID: fdf9e337538a
Revises: 19cf76d2d459
Create Date: 2022-03-21 17:02:22.924858
"""

import sqlalchemy as sa

from alembic import op

revision = "fdf9e337538a"
down_revision = "19cf76d2d459"


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "is_frozen", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )


def downgrade():
    op.drop_column("users", "is_frozen")
