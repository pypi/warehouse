# SPDX-License-Identifier: Apache-2.0
"""
Bump metadata fields

Revision ID: 66fb4fedd34b
Revises: 31ac9b5e1e8b
Create Date: 2026-01-23 19:31:12.626657
"""

from alembic import op
from alembic_postgresql_enum import ColumnType, TableReference

revision = "66fb4fedd34b"
down_revision = "31ac9b5e1e8b"


def upgrade():
    op.execute("""
        ALTER TYPE public.release_dynamic_fields
        ADD VALUE IF NOT EXISTS 'Import-Name'
        """)
    op.execute("""
        ALTER TYPE public.release_dynamic_fields
        ADD VALUE IF NOT EXISTS 'Import-Namespace'
        """)


def downgrade():
    op.sync_enum_values(
        enum_schema="public",
        enum_name="release_dynamic_fields",
        new_values=[
            "Platform",
            "Supported-Platform",
            "Summary",
            "Description",
            "Description-Content-Type",
            "Keywords",
            "Home-Page",
            "Download-Url",
            "Author",
            "Author-Email",
            "Maintainer",
            "Maintainer-Email",
            "License",
            "License-Expression",
            "License-File",
            "Classifier",
            "Requires-Dist",
            "Requires-Python",
            "Requires-External",
            "Project-Url",
            "Provides-Extra",
            "Provides-Dist",
            "Obsoletes-Dist",
            "Requires",
            "Provides",
            "Obsoletes",
        ],
        affected_columns=[
            TableReference(
                table_schema="public",
                table_name="releases",
                column_name="dynamic",
                column_type=ColumnType.ARRAY,
            )
        ],
        enum_values_to_rename=[],
    )
