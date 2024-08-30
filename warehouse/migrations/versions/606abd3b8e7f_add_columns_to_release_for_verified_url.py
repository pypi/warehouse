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
Add columns to Release for verified URL status

Revision ID: 606abd3b8e7f
Revises: 7ca0f1f5e7b3
Create Date: 2024-08-26 08:31:32.734838
"""

import sqlalchemy as sa

from alembic import op

revision = "606abd3b8e7f"
down_revision = "7ca0f1f5e7b3"


def upgrade():
    op.add_column(
        "releases",
        sa.Column(
            "home_page_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "releases",
        sa.Column(
            "download_url_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("releases", "download_url_verified")
    op.drop_column("releases", "home_page_verified")
