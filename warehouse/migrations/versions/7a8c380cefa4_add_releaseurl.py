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
add ReleaseURL

Revision ID: 7a8c380cefa4
Revises: d1c00b634ac8
Create Date: 2022-06-10 22:02:49.522320
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "7a8c380cefa4"
down_revision = "d1c00b634ac8"


def upgrade():
    op.create_table(
        "release_urls",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("release_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["release_id"], ["releases.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("release_id", "name"),
    )
    op.create_index(
        op.f("ix_release_urls_release_id"), "release_urls", ["release_id"], unique=False
    )


def downgrade():
    op.drop_index(op.f("ix_release_urls_release_id"), table_name="release_urls")
    op.drop_table("release_urls")
