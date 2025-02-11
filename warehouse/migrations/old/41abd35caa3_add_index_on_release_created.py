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
Add Index on Release.created

Revision ID: 41abd35caa3
Revises: 3af8d0006ba
Create Date: 2015-08-24 23:16:07.674157
"""

import sqlalchemy as sa

from alembic import op

revision = "41abd35caa3"
down_revision = "3af8d0006ba"


def upgrade():
    op.create_index(
        "release_created_idx", "releases", [sa.text("created DESC")], unique=False
    )


def downgrade():
    op.drop_index("release_created_idx", table_name="releases")
