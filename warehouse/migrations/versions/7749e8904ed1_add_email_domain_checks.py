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
Add Email domain checks

Revision ID: 7749e8904ed1
Revises: 6de76386dbf4
Create Date: 2025-03-20 16:29:11.719769
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "7749e8904ed1"
down_revision = "6de76386dbf4"


def upgrade():
    op.add_column(
        "user_emails",
        sa.Column(
            "domain_last_checked",
            sa.DateTime(),
            nullable=True,
            comment="Last time domain was checked with the domain validation service.",
        ),
    )
    op.add_column(
        "user_emails",
        sa.Column(
            "domain_last_status",
            postgresql.ARRAY(sa.String()),
            nullable=True,
            comment="Status strings returned by the domain validation service.",
        ),
    )


def downgrade():
    op.drop_column("user_emails", "domain_last_status")
    op.drop_column("user_emails", "domain_last_checked")
