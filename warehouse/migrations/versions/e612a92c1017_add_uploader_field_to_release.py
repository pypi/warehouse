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

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e612a92c1017"
down_revision = "5538f2d929dd"


def upgrade():
    op.add_column(
        "releases",
        sa.Column("uploader_id", postgresql.UUID(as_uuid=True), nullable=True),
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
