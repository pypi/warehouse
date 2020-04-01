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
add description-content-type field

Revision ID: 5dda74213989
Revises: 2730e54f8717
Create Date: 2017-09-08 21:15:55.822175
"""

import sqlalchemy as sa

from alembic import op

revision = "5dda74213989"
down_revision = "2730e54f8717"


def upgrade():
    op.add_column(
        "releases", sa.Column("description_content_type", sa.Text(), nullable=True)
    )


def downgrade():
    op.drop_column("releases", "description_content_type")
