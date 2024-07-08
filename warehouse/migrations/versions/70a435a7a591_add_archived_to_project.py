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
add archived to Project

Revision ID: 70a435a7a591
Revises: 78ecf599841c
Create Date: 2024-05-13 15:56:13.050983
"""

import sqlalchemy as sa

from alembic import op

revision = "70a435a7a591"
down_revision = "78ecf599841c"


def upgrade():
    op.add_column(
        "projects",
        sa.Column(
            "archived", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )


def downgrade():
    op.drop_column("projects", "archived")