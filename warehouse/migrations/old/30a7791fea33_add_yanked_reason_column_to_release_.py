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
Add yanked_reason column to Release table

Revision ID: 30a7791fea33
Revises: 43b0e796a40d
Create Date: 2020-05-09 20:25:19.454034
"""

import sqlalchemy as sa

from alembic import op

revision = "30a7791fea33"
down_revision = "43b0e796a40d"


def upgrade():
    op.add_column(
        "releases",
        sa.Column("yanked_reason", sa.Text(), server_default="", nullable=False),
    )


def downgrade():
    op.drop_column("releases", "yanked_reason")
