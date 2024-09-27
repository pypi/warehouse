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
Add verified emails columns to Release

Revision ID: 0b74ed7d4880
Revises: 2e049cda494f
Create Date: 2024-09-04 14:04:12.622697
"""

import sqlalchemy as sa

from alembic import op

revision = "0b74ed7d4880"
down_revision = "2e049cda494f"


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text("SET statement_timeout = 120000"))
    conn.execute(sa.text("SET lock_timeout = 120000"))

    op.add_column(
        "releases",
        sa.Column(
            "author_email_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE releases
        SET author_email_verified = false
        WHERE author_email_verified IS NULL
    """
    )
    op.alter_column("releases", "author_email_verified", nullable=False)

    op.add_column(
        "releases",
        sa.Column(
            "maintainer_email_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE releases
        SET maintainer_email_verified = false
        WHERE maintainer_email_verified IS NULL
    """
    )
    op.alter_column("releases", "maintainer_email_verified", nullable=False)


def downgrade():
    op.drop_column("releases", "maintainer_email_verified")
    op.drop_column("releases", "author_email_verified")
