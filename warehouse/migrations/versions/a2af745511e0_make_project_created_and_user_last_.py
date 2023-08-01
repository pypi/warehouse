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
Make Project.created and User.last_login nullable

Revision ID: a2af745511e0
Revises: 4a0276f260c7
Create Date: 2023-08-01 20:15:14.122464
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a2af745511e0"
down_revision = "4a0276f260c7"


def upgrade():
    op.execute("SET statement_timeout = 5000")
    op.execute("SET lock_timeout = 4000")

    op.alter_column(
        "projects",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "users",
        "last_login",
        existing_type=postgresql.TIMESTAMP(),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )

    # Data migration
    op.execute("UPDATE projects SET created = NULL where created = '-infinity'")
    op.execute("UPDATE users SET last_login = NULL where last_login = '-infinity'")


def downgrade():
    op.alter_column(
        "users",
        "last_login",
        existing_type=postgresql.TIMESTAMP(),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "projects",
        "created",
        existing_type=postgresql.TIMESTAMP(),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )

    # Data migration
    op.execute("UPDATE projects SET created = '-infinity' where created = NULL")
    op.execute("UPDATE users SET last_login = '-infinity' where last_login = NULL")
