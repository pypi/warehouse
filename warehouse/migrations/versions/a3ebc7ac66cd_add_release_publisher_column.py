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
Add Release.publisher column

Revision ID: a3ebc7ac66cd
Revises: eb736cb3236d
Create Date: 2023-03-09 16:32:16.368787
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a3ebc7ac66cd"
down_revision = "eb736cb3236d"


def upgrade():
    op.add_column(
        "releases",
        sa.Column("oidc_publisher_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        op.f("ix_releases_oidc_publisher_id"),
        "releases",
        ["oidc_publisher_id"],
        unique=False,
    )
    op.create_foreign_key(
        None,
        "releases",
        "oidc_publishers",
        ["oidc_publisher_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint(None, "releases", type_="foreignkey")
    op.drop_index(op.f("ix_releases_oidc_publisher_id"), table_name="releases")
    op.drop_column("releases", "oidc_publisher_id")
