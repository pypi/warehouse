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
remove admin_squats table

Revision ID: 99a201142761
Revises: b6d057388dd9
Create Date: 2020-11-10 12:41:25.765722
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "99a201142761"
down_revision = "b6d057388dd9"


def upgrade():
    op.drop_table("admin_squats")


def downgrade():
    op.create_table(
        "admin_squats",
        sa.Column("id", sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column(
            "created",
            postgresql.TIMESTAMP(),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "reviewed",
            sa.BOOLEAN(),
            server_default=sa.text("false"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "squattee_id", postgresql.UUID(), autoincrement=False, nullable=False
        ),
        sa.Column(
            "squatter_id", postgresql.UUID(), autoincrement=False, nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["squattee_id"],
            ["projects.id"],
            name="admin_squats_squattee_id_fkey",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["squatter_id"],
            ["projects.id"],
            name="admin_squats_squatter_id_fkey",
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="admin_squats_pkey"),
    )
