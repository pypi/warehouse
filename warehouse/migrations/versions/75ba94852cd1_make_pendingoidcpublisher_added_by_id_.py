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
Make PendingOIDCPublisher.added_by_id non-nullable

Revision ID: 75ba94852cd1
Revises: f7cd7a943caa
Create Date: 2023-04-14 18:21:38.683694
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "75ba94852cd1"
down_revision = "f7cd7a943caa"


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text("SET statement_timeout = 120000"))
    conn.execute(sa.text("SET lock_timeout = 120000"))
    op.alter_column(
        "pending_oidc_publishers",
        "added_by_id",
        existing_type=postgresql.UUID(),
        nullable=False,
    )


def downgrade():
    op.alter_column(
        "pending_oidc_publishers",
        "added_by_id",
        existing_type=postgresql.UUID(),
        nullable=True,
    )
