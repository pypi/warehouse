# SPDX-License-Identifier: Apache-2.0
"""
Bump metadata fields

Revision ID: 31ca82c94aa6
Revises: a6cae8e65f1a
Create Date: 2026-01-12 22:01:38.715040
"""

import sqlalchemy as sa

from alembic import op
from alembic_postgresql_enum import ColumnType, TableReference

revision = "31ca82c94aa6"
down_revision = "a6cae8e65f1a"


def upgrade():
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
            "Import-Name",
            "Import-Namespace",
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
