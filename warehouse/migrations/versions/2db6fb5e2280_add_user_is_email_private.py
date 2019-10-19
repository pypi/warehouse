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
add User.is_email_private

Revision ID: 2db6fb5e2280
Revises: ee4c59b2ef3a
Create Date: 2019-10-12 21:22:02.654837
"""

import sqlalchemy as sa

from alembic import op

revision = "2db6fb5e2280"
down_revision = "ee4c59b2ef3a"


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "is_email_private",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("users", "is_email_private")
