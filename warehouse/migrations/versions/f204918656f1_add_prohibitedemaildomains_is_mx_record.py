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
Add ProhibitedEmailDomains.is_mx_record

Revision ID: f204918656f1
Revises: 1b9ae6ec6ec0
Create Date: 2024-09-09 20:04:30.136554
"""

import sqlalchemy as sa

from alembic import op

revision = "f204918656f1"
down_revision = "1b9ae6ec6ec0"


def upgrade():
    op.add_column(
        "prohibited_email_domains",
        sa.Column(
            "is_mx_record",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=True,
            comment="Prohibit any domains that have this domain as an MX record?",
        ),
    )
    op.execute(
        """
        UPDATE prohibited_email_domains
        SET is_mx_record = false
        WHERE is_mx_record IS NULL
    """
    )
    op.alter_column("prohibited_email_domains", "is_mx_record", nullable=False)


def downgrade():
    op.drop_column("prohibited_email_domains", "is_mx_record")
