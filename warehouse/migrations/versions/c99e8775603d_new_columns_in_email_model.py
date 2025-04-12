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
"""New Columns in Email Model

Revision ID: c99e8775603d
Revises: 4f8982e60deb
Create Date: 2025-04-12 18:45:40.713109

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects.postgresql import CITEXT

# revision identifiers, used by Alembic.
revision = "c99e8775603d"
down_revision = "4f8982e60deb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add columns
    op.add_column("user_emails", sa.Column("normalized_email", CITEXT()))
    op.add_column("user_emails", sa.Column("domain", CITEXT()))

    # Populate data
    op.execute(
        """
        UPDATE user_emails 
        SET normalized_email = LOWER(email),
            domain = LOWER(SPLIT_PART(email, '@', 2))
    """
    )

    # Add constraints
    op.alter_column("user_emails", "normalized_email", nullable=False)
    op.alter_column("user_emails", "domain", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop columns
    op.drop_column("user_emails", "domain")
    op.drop_column("user_emails", "normalized_email")
