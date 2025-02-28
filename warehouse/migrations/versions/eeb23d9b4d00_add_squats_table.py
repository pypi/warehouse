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
add squats table

Revision ID: eeb23d9b4d00
Revises: 56e9e630c748
Create Date: 2018-11-03 06:05:42.158355
"""

import sqlalchemy as sa

from alembic import op

revision = "eeb23d9b4d00"
down_revision = "56e9e630c748"


def upgrade():
    op.create_table(
        "warehouse_admin_squat",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("squatter_name", sa.Text(), nullable=True),
        sa.Column("squattee_name", sa.Text(), nullable=True),
        sa.Column(
            "reviewed", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["squattee_name"], ["packages.name"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["squatter_name"], ["packages.name"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("warehouse_admin_squat")
