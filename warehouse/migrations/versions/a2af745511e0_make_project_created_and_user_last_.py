# SPDX-License-Identifier: Apache-2.0
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
