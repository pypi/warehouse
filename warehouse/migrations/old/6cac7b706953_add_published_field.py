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
add published field

Revision ID: 6cac7b706953
Revises: 2a2c32c47a8f
Create Date: 2025-01-22 08:49:17.030343
"""

import sqlalchemy as sa

from alembic import op

revision = "6cac7b706953"
down_revision = "2a2c32c47a8f"


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text("SET statement_timeout = 120000"))
    conn.execute(sa.text("SET lock_timeout = 120000"))

    op.add_column(
        "releases",
        sa.Column(
            "published", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
    )


def downgrade():
    op.drop_column("releases", "published")
