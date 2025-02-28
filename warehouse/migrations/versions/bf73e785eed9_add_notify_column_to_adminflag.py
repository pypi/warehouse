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
Add notify column to AdminFlag

Revision ID: bf73e785eed9
Revises: 5dda74213989
Create Date: 2018-03-23 21:20:05.834821
"""

import sqlalchemy as sa

from alembic import op

revision = "bf73e785eed9"
down_revision = "5dda74213989"


def upgrade():
    op.add_column(
        "warehouse_admin_flag",
        sa.Column(
            "notify", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )


def downgrade():
    op.drop_column("warehouse_admin_flag", "notify")
