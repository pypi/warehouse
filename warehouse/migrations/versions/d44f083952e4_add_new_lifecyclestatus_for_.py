# SPDX-License-Identifier: Apache-2.0
"""
Add new LifecycleStatus for ArchivedNoindex

Revision ID: d44f083952e4
Revises: 6de76386dbf4
Create Date: 2025-03-27 14:37:10.791465
"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "d44f083952e4"
down_revision = "6de76386dbf4"


def upgrade():
    op.execute(
        "ALTER TYPE public.lifecyclestatus ADD VALUE IF NOT EXISTS 'archived-noindex'"
    )


def downgrade():
    op.sync_enum_values(
        enum_schema="public",
        enum_name="lifecyclestatus",
        new_values=["quarantine-enter", "quarantine-exit", "archived"],
        affected_columns=[
            TableReference(
                table_schema="public",
                table_name="projects",
                column_name="lifecycle_status",
            )
        ],
        enum_values_to_rename=[],
    )
