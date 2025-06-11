# SPDX-License-Identifier: Apache-2.0
"""
add admin initiated password reset

Revision ID: 82b2ebed68b6
Revises: 14ad61e054cf
Create Date: 2024-07-09 21:18:50.979790
"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "82b2ebed68b6"
down_revision = "14ad61e054cf"


def upgrade():
    op.execute("SET statement_timeout = 60000")
    op.execute("SET lock_timeout = 10000")
    op.sync_enum_values(
        "public",
        "disablereason",
        ["password compromised", "account frozen", "admin initiated"],
        [
            TableReference(
                table_schema="public", table_name="users", column_name="disabled_for"
            )
        ],
        enum_values_to_rename=[],
    )


def downgrade():
    op.execute("SET statement_timeout = 60000")
    op.execute("SET lock_timeout = 10000")
    op.sync_enum_values(
        "public",
        "disablereason",
        ["password compromised", "account frozen"],
        [
            TableReference(
                table_schema="public", table_name="users", column_name="disabled_for"
            )
        ],
        enum_values_to_rename=[],
    )
