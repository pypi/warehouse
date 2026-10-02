# SPDX-License-Identifier: Apache-2.0
"""
Add ADMINISTRATIVE to BanReason enum

Revision ID: 31ac9b5e1e8b
Revises: a6cae8e65f1a
Create Date: 2025-12-22 18:19:43.751813
"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "31ac9b5e1e8b"
down_revision = "a6cae8e65f1a"


def upgrade():
    op.execute("ALTER TYPE public.banreason ADD VALUE IF NOT EXISTS 'administrative'")


def downgrade():
    op.sync_enum_values(
        enum_schema="public",
        enum_name="banreason",
        new_values=["authentication-attempts"],
        affected_columns=[
            TableReference(
                table_schema="public",
                table_name="ip_addresses",
                column_name="ban_reason",
            )
        ],
        enum_values_to_rename=[],
    )
