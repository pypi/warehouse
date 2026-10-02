# SPDX-License-Identifier: Apache-2.0
"""
Bump metadata fields

Revision ID: 28c1e0646708
Revises: a6045de6d1fe
Create Date: 2026-02-10 18:32:06.895984
"""

from alembic import op
from alembic_postgresql_enum import ColumnType, TableReference

revision = "28c1e0646708"
down_revision = "a6045de6d1fe"


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
