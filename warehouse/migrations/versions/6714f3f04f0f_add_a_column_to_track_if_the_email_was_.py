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
Add a column to track if the email was missing

Revision ID: 6714f3f04f0f
Revises: 7f0d1b5af8c7
Create Date: 2018-04-15 06:05:36.949018
"""

import sqlalchemy as sa

from alembic import op

revision = "6714f3f04f0f"
down_revision = "7f0d1b5af8c7"


def upgrade():
    op.add_column(
        "ses_emails",
        sa.Column(
            "missing", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )


def downgrade():
    op.drop_column("ses_emails", "missing")
