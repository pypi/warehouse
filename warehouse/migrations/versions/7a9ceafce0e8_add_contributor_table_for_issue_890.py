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
Add contributor table for issue #890

Revision ID: 7a9ceafce0e8
Revises: 6af76ffb9612
Create Date: 2018-05-13 01:23:43.819114
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "7a9ceafce0e8"
down_revision = "6af76ffb9612"


def upgrade():
    op.create_table(
        "warehouse_contributors",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("contributor_login", sa.Text(), nullable=False),
        sa.Column("contributor_name", sa.Text(), nullable=False),
        sa.Column("contributor_url", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", "contributor_login"),
        sa.UniqueConstraint("contributor_login"),
    )


def downgrade():
    op.drop_table("warehouse_contributors")
