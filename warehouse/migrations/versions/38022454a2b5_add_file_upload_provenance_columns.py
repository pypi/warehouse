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
Add File upload provenance columns

Revision ID: 38022454a2b5
Revises: eb736cb3236d
Create Date: 2023-03-09 19:10:28.260469
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "38022454a2b5"
down_revision = "eb736cb3236d"


def upgrade():
    op.add_column(
        "release_files",
        sa.Column("uploading_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "release_files",
        sa.Column("oidc_publisher_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        op.f("ix_release_files_oidc_publisher_id"),
        "release_files",
        ["oidc_publisher_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_release_files_uploading_user_id"),
        "release_files",
        ["uploading_user_id"],
        unique=False,
    )
    op.create_foreign_key(
        None,
        "release_files",
        "users",
        ["uploading_user_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        None,
        "release_files",
        "oidc_publishers",
        ["oidc_publisher_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint(None, "release_files", type_="foreignkey")
    op.drop_constraint(None, "release_files", type_="foreignkey")
    op.drop_index(
        op.f("ix_release_files_uploading_user_id"), table_name="release_files"
    )
    op.drop_index(
        op.f("ix_release_files_oidc_publisher_id"), table_name="release_files"
    )
    op.drop_column("release_files", "oidc_publisher_id")
    op.drop_column("release_files", "uploading_user_id")
