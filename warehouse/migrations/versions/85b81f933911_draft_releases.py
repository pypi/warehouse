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
Draft Releases

Revision ID: 85b81f933911
Revises: a8050411bc65
Create Date: 2024-09-21 03:49:20.048416
"""

import sqlalchemy as sa

from alembic import op

revision = "85b81f933911"
down_revision = "a8050411bc65"


def upgrade():
    op.add_column("releases", sa.Column("project_name", sa.Text(), nullable=True))
    op.add_column(
        "releases",
        sa.Column(
            "published", sa.DateTime(), server_default=sa.text("now()"), nullable=True
        ),
    )
    # Fill the project_name and published columns.
    op.execute(
        """
        UPDATE releases AS target SET published = (
        SELECT created
        FROM releases AS source WHERE source.id = target.id
        );
    """
    )
    op.execute(
        """
        UPDATE releases AS r SET project_name = (
            SELECT name
            FROM projects AS p WHERE p.id = r.project_id
        )
    """
    )

    # Create the hashing database function for our draft identifiers
    op.execute(
        """
        CREATE FUNCTION make_draft_hash(project_name text, version text)
        returns text as $$
                SELECT  md5(project_name || version)
            $$
            LANGUAGE SQL
            IMMUTABLE
            RETURNS NULL ON NULL INPUT;
    """
    )


def downgrade():
    op.drop_column("releases", "published")
    op.drop_column("releases", "project_name")
    op.execute("DROP FUNCTION make_draft_hash")
