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
macaroon oidc claims

Revision ID: 646bc86a09b6
Revises: 60e6b0dd0f47
Create Date: 2023-06-01 16:50:32.765849
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "646bc86a09b6"
down_revision = "60e6b0dd0f47"


def upgrade():
    op.add_column(
        "macaroons",
        sa.Column("additional", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade():
    op.drop_column("macaroons", "additional")
