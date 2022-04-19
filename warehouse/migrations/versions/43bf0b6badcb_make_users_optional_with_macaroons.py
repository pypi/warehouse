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
Make users optional with Macaroons

Revision ID: 43bf0b6badcb
Revises: 84262e097c26
Create Date: 2022-04-19 14:57:54.765006
"""

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "43bf0b6badcb"
down_revision = "84262e097c26"


def upgrade():
    op.alter_column(
        "macaroons", "user_id", existing_type=postgresql.UUID(), nullable=True
    )


def downgrade():
    op.alter_column(
        "macaroons", "user_id", existing_type=postgresql.UUID(), nullable=False
    )
