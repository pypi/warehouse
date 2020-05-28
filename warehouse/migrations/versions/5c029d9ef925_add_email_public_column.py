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
add email.public column

Revision ID: 5c029d9ef925
Revises: e133fc5aa3c1
Create Date: 2020-01-19 22:25:53.901148
"""

import sqlalchemy as sa

from alembic import op

revision = "5c029d9ef925"
down_revision = "e133fc5aa3c1"


def upgrade():
    op.add_column(
        "user_emails",
        sa.Column(
            "public", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )


def downgrade():
    op.drop_column("user_emails", "public")
