# SPDX-License-Identifier: Apache-2.0
"""
Add new LifecycleStatus for Deprecated

Revision ID: d3dac0f3bb25
Revises: 423ffda7411f
Create Date: 2026-07-22 00:00:00.000000
"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "d3dac0f3bb25"
down_revision = "423ffda7411f"


def upgrade():
    op.execute("ALTER TYPE public.lifecyclestatus ADD VALUE IF NOT EXISTS 'deprecated'")


def downgrade():
    op.sync_enum_values(
        enum_schema="public",
        enum_name="lifecyclestatus",
        new_values=[
            "quarantine-enter",
            "quarantine-exit",
            "archived",
            "archived-noindex",
        ],
        affected_columns=[
            TableReference(
                table_schema="public",
                table_name="projects",
                column_name="lifecycle_status",
            ),
            TableReference(
                table_schema="public",
                table_name="releases",
                column_name="lifecycle_status",
            ),
        ],
        enum_values_to_rename=[],
    )
