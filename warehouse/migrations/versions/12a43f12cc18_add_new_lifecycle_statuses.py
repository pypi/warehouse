# SPDX-License-Identifier: Apache-2.0
"""
Add new lifecycle statuses

Revision ID: 12a43f12cc18
Revises: 24aa37164e72
"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "12a43f12cc18"
down_revision = "24aa37164e72"


def upgrade():
    op.execute("ALTER TYPE public.lifecyclestatus ADD VALUE IF NOT EXISTS 'archived'")


def downgrade():
    op.sync_enum_values(
        "public",
        "lifecyclestatus",
        ["quarantine-enter", "quarantine-exit"],
        [
            TableReference(
                table_schema="public",
                table_name="projects",
                column_name="lifecycle_status",
            )
        ],
        enum_values_to_rename=[],
    )
