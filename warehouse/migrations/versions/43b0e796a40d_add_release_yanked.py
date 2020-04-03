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
Add Release.yanked

Revision ID: 43b0e796a40d
Revises: d15f020ee3df
Create Date: 2020-03-13 03:31:03.153039
"""

import sqlalchemy as sa

from alembic import op

revision = "43b0e796a40d"
down_revision = "d15f020ee3df"


def upgrade():
    op.add_column(
        "releases",
        sa.Column(
            "yanked", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )


def downgrade():
    op.drop_column("releases", "yanked")
