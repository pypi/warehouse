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
Add uploader field to Release

Revision ID: e612a92c1017
Revises: 5538f2d929dd
Create Date: 2018-11-06 16:22:01.484362
"""

from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql


revision = "e612a92c1017"
down_revision = "5538f2d929dd"


def upgrade():
    op.add_column(
        "releases",
        sa.Column("uploader_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        """
        UPDATE releases
        SET uploader_id = s.user_id
        FROM (
            SELECT accounts_user.id as user_id,
                    packages.id as project_id,
                    releases.version as release_version,
                    ROW_NUMBER() OVER (
                        PARTITION BY journals.name, journals.version
                        ORDER BY journals.id DESC
                    ) as rn
            FROM accounts_user, packages, journals, releases
            WHERE journals.name = packages.name
                AND journals.version = releases.version
                AND journals.action = 'new release'
                AND accounts_user.username = journals.submitted_by
        ) s
        WHERE releases.project_id = s.project_id
            AND releases.version = s.release_version
            AND s.rn = 1
        """
    )
    op.create_foreign_key(
        None,
        "releases",
        "accounts_user",
        ["uploader_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="SET NULL",
    )
    op.create_index("ix_releases_uploader_id", "releases", ["uploader_id"])


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
