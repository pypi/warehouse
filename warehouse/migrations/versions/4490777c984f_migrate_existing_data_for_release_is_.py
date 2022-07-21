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
Migrate Existing Data for Release.is_prerelease

Revision ID: 4490777c984f
Revises: b0dbcd2f5c77
Create Date: 2022-06-27 17:49:09.835384
"""

import sqlalchemy as sa

from alembic import op

revision = "4490777c984f"
down_revision = "b0dbcd2f5c77"


def upgrade():
    op.execute(
        """
        UPDATE releases
        SET is_prerelease = pep440_is_prerelease(version)
        WHERE is_prerelease IS NULL
        """
    )
    op.alter_column(
        "releases",
        "is_prerelease",
        existing_type=sa.BOOLEAN(),
        server_default=sa.text("false"),
        nullable=False,
    )


def downgrade():
    op.alter_column(
        "releases",
        "is_prerelease",
        existing_type=sa.BOOLEAN(),
        server_default=None,
        nullable=True,
    )
