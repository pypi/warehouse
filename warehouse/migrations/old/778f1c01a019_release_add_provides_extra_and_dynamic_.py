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
release: add provides_extra and dynamic columns

Revision ID: 778f1c01a019
Revises: 81f9f9a60270
Create Date: 2023-10-12 13:04:25.039108
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "778f1c01a019"
down_revision = "81f9f9a60270"


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text("SET statement_timeout = 120000"))
    sa.Enum(
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
        name="release_dynamic_fields",
    ).create(conn)
    op.add_column(
        "releases",
        sa.Column(
            "dynamic",
            postgresql.ARRAY(
                postgresql.ENUM(
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
                    name="release_dynamic_fields",
                )
            ),
            nullable=True,
            comment="Array of metadata fields marked as Dynamic (PEP 643/Metadata 2.2)",
        ),
    )
    op.add_column(
        "releases",
        sa.Column(
            "provides_extra",
            postgresql.ARRAY(sa.Text()),
            nullable=True,
            comment="Array of extra names (PEP 566/685|Metadata 2.1/2.3)",
        ),
    )


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("SET statement_timeout = 120000"))
    op.drop_column("releases", "provides_extra")
    op.drop_column("releases", "dynamic")
    sa.Enum(
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
        name="release_dynamic_fields",
    ).drop(conn)
