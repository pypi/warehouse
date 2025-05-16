# SPDX-License-Identifier: Apache-2.0
"""
add pep 639 columns

Revision ID: 6ee23f5a6c1b
Revises: 2af8015830dd
Create Date: 2024-10-22 16:50:16.504506
"""

import sqlalchemy as sa

from alembic import op
from alembic_postgresql_enum import ColumnType, TableReference
from sqlalchemy.dialects import postgresql

revision = "6ee23f5a6c1b"
down_revision = "2af8015830dd"


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text("SET statement_timeout = 120000"))
    conn.execute(sa.text("SET lock_timeout = 120000"))

    op.add_column(
        "releases", sa.Column("license_expression", sa.String(), nullable=True)
    )
    op.add_column(
        "releases",
        sa.Column(
            "license_files",
            postgresql.ARRAY(sa.String()),
            nullable=True,
            comment=(
                "Array of license filenames. "
                "Null indicates no License-File(s) were supplied by the uploader."
            ),
        ),
    )
    op.sync_enum_values(
        "public",
        "release_dynamic_fields",
        [
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
        ],
        [
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
        "public",
        "release_dynamic_fields",
        [
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
            "Classifier",
            "Requires-Dist",
            "Requires-Python",
            "Requires-External",
            "Project-Url",
            "Provides-Extra",
            "Provides-Dist",
            "Obsoletes-Dist",
        ],
        [
            TableReference(
                table_schema="public",
                table_name="releases",
                column_name="dynamic",
                column_type=ColumnType.ARRAY,
            )
        ],
        enum_values_to_rename=[],
    )
    op.drop_column("releases", "license_files")
    op.drop_column("releases", "license_expression")
