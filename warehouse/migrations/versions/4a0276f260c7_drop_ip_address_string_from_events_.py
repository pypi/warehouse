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
drop ip_address_string from events tables

Revision ID: 4a0276f260c7
Revises: 34cccbcab226
Create Date: 2023-06-11 12:03:05.180213
"""

import sqlalchemy as sa

from alembic import op

revision = "4a0276f260c7"
down_revision = "34cccbcab226"


def upgrade():
    op.drop_column("file_events", "ip_address_string")
    op.drop_column("organization_events", "ip_address_string")
    op.drop_column("project_events", "ip_address_string")
    op.drop_column("team_events", "ip_address_string")
    op.drop_column("user_events", "ip_address_string")


def downgrade():
    op.add_column(
        "user_events",
        sa.Column(
            "ip_address_string", sa.VARCHAR(), autoincrement=False, nullable=True
        ),
    )
    op.add_column(
        "team_events",
        sa.Column(
            "ip_address_string", sa.VARCHAR(), autoincrement=False, nullable=True
        ),
    )
    op.add_column(
        "project_events",
        sa.Column(
            "ip_address_string", sa.VARCHAR(), autoincrement=False, nullable=True
        ),
    )
    op.add_column(
        "organization_events",
        sa.Column(
            "ip_address_string", sa.VARCHAR(), autoincrement=False, nullable=True
        ),
    )
    op.add_column(
        "file_events",
        sa.Column(
            "ip_address_string", sa.VARCHAR(), autoincrement=False, nullable=True
        ),
    )
