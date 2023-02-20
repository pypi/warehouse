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
Add Release.keywords_array column

Revision ID: 677b8c232e17
Revises: f93cf2d43974
Create Date: 2023-02-14 19:32:12.553294
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "677b8c232e17"
down_revision = "f93cf2d43974"


def upgrade():
    op.add_column(
        "releases",
        sa.Column("keywords_array", postgresql.ARRAY(sa.Text()), nullable=True),
    )
    # Fill the new column with the data from the keywords column
    # Splits the keywords column on commas and trims the whitespace
    op.execute(
        """
        UPDATE releases
        SET keywords_array = (
            SELECT ARRAY(
                SELECT TRIM(
                    UNNEST(
                        STRING_TO_ARRAY(keywords, ',')
                    )
                )
            )
        )
        WHERE keywords IS NOT NULL AND keywords != ''
        """
    )


def downgrade():
    op.drop_column("releases", "keywords_array")
