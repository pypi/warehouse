# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Correct Dynamic Field Normalization

Revision ID: b14df478c48f
Revises: cec0316503a5
Create Date: 2024-06-17 14:20:18.254557
"""

from alembic import op
from alembic_postgresql_enum import ColumnType, TableReference

revision = "b14df478c48f"
down_revision = "cec0316503a5"


def upgrade():
    op.execute("SET statement_timeout = 60000")
    op.execute("SET lock_timeout = 60000")
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
        enum_values_to_rename=[
            ("Home-page", "Home-Page"),
            ("Download-URL", "Download-Url"),
            ("Author-email", "Author-Email"),
            ("Maintainer-email", "Maintainer-Email"),
            ("Project-URL", "Project-Url"),
        ],
    )


def downgrade():
    op.execute("SET statement_timeout = 60000")
    op.execute("SET lock_timeout = 60000")
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
            "Home-page",
            "Download-URL",
            "Author",
            "Author-email",
            "Maintainer",
            "Maintainer-email",
            "License",
            "Classifier",
            "Requires-Dist",
            "Requires-Python",
            "Requires-External",
            "Project-URL",
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
        enum_values_to_rename=[
            ("Home-Page", "Home-page"),
            ("Download-Url", "Download-URL"),
            ("Author-Email", "Author-email"),
            ("Maintainer-Email", "Maintainer-email"),
            ("Project-Url", "Project-URL"),
        ],
    )
