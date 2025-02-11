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
Add is_support to User

Revision ID: bb6943882aa9
Revises: c79e12731fcd
Create Date: 2024-07-15 13:55:49.978586
"""

import sqlalchemy as sa

from alembic import op

revision = "bb6943882aa9"
down_revision = "c79e12731fcd"


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "is_support", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )


def downgrade():
    op.drop_column("users", "is_support")
