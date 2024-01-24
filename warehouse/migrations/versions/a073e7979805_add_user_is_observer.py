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
Add User.is_observer

Revision ID: 5224f11972be
Revises: 812e14a4cddf
Create Date: 2024-01-18 23:48:27.127394
"""

import sqlalchemy as sa

from alembic import op

revision = "a073e7979805"
down_revision = "812e14a4cddf"


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "is_observer",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
            comment="Is this user allowed to add Observations?",
        ),
    )


def downgrade():
    op.drop_column("users", "is_observer")
