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
Add prohibited username table

Revision ID: ad71523546f9
Revises: 6e003184453d
Create Date: 2022-05-19 21:28:31.695167
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "ad71523546f9"
down_revision = "6e003184453d"


def upgrade():
    op.create_table(
        "prohibited_user_names",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("prohibited_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("comment", sa.Text(), server_default="", nullable=False),
        sa.CheckConstraint(
            "name ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'",
            name="prohibited_users_valid_username",
        ),
        sa.CheckConstraint(
            "length(name) <= 50", name="prohibited_users_valid_username_length"
        ),
        sa.ForeignKeyConstraint(
            ["prohibited_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        op.f("ix_prohibited_user_names_prohibited_by"),
        "prohibited_user_names",
        ["prohibited_by"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_prohibited_user_names_prohibited_by"),
        table_name="prohibited_user_names",
    )
    op.drop_table("prohibited_user_names")
