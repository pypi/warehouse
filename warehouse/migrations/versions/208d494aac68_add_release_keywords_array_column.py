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

Revision ID: 208d494aac68
Revises: fd06c4fe2f97
Create Date: 2024-08-02 19:02:01.760253
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "208d494aac68"
down_revision = "fd06c4fe2f97"


def upgrade():
    op.add_column(
        "releases",
        sa.Column(
            "keywords_array",
            postgresql.ARRAY(sa.String()),
            nullable=True,
            comment=(
                "Array of keywords. Null indicates no keywords were supplied by "
                "the uploader."
            ),
        ),
    )


def downgrade():
    op.drop_column("releases", "keywords_array")
