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
Add details and fixed_in to VulnerabilityRecords

Revision ID: d582fb87b94c
Revises: 1dbb95161e5a
Create Date: 2021-10-14 17:32:40.849906
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d582fb87b94c"
down_revision = "1dbb95161e5a"


def upgrade():
    op.add_column("vulnerabilities", sa.Column("details", sa.String(), nullable=True))
    op.add_column(
        "vulnerabilities",
        sa.Column("fixed_in", postgresql.ARRAY(sa.String()), nullable=True),
    )


def downgrade():
    op.drop_column("vulnerabilities", "fixed_in")
    op.drop_column("vulnerabilities", "details")
