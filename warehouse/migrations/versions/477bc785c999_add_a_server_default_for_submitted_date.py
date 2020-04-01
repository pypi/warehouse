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
Add a server default for submitted_date

Revision ID: 477bc785c999
Revises: 6a03266b2d
Create Date: 2015-12-16 16:19:59.419186
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "477bc785c999"
down_revision = "6a03266b2d"


def upgrade():
    op.alter_column(
        "journals", "submitted_date", server_default=sa.func.now(), nullable=False
    )


def downgrade():
    op.alter_column(
        "journals",
        "submitted_date",
        existing_type=postgresql.TIMESTAMP(),
        server_default=None,
        nullable=True,
    )
