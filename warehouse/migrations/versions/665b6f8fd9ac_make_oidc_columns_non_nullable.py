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
Make OIDC columns non-nullable

Revision ID: 665b6f8fd9ac
Revises: 203f1f8dcf92
Create Date: 2023-04-10 22:02:56.025979
"""

import sqlalchemy as sa

from alembic import op

revision = "665b6f8fd9ac"
down_revision = "203f1f8dcf92"


def upgrade():
    op.alter_column(
        "github_oidc_publishers",
        "repository_name",
        existing_type=sa.VARCHAR(),
        nullable=False,
    )
    op.alter_column(
        "github_oidc_publishers",
        "repository_owner",
        existing_type=sa.VARCHAR(),
        nullable=False,
    )
    op.alter_column(
        "github_oidc_publishers",
        "repository_owner_id",
        existing_type=sa.VARCHAR(),
        nullable=False,
    )
    op.alter_column(
        "github_oidc_publishers",
        "workflow_filename",
        existing_type=sa.VARCHAR(),
        nullable=False,
    )
    op.alter_column(
        "pending_github_oidc_publishers",
        "repository_name",
        existing_type=sa.VARCHAR(),
        nullable=False,
    )
    op.alter_column(
        "pending_github_oidc_publishers",
        "repository_owner",
        existing_type=sa.VARCHAR(),
        nullable=False,
    )
    op.alter_column(
        "pending_github_oidc_publishers",
        "repository_owner_id",
        existing_type=sa.VARCHAR(),
        nullable=False,
    )
    op.alter_column(
        "pending_github_oidc_publishers",
        "workflow_filename",
        existing_type=sa.VARCHAR(),
        nullable=False,
    )


def downgrade():
    op.alter_column(
        "pending_github_oidc_publishers",
        "workflow_filename",
        existing_type=sa.VARCHAR(),
        nullable=True,
    )
    op.alter_column(
        "pending_github_oidc_publishers",
        "repository_owner_id",
        existing_type=sa.VARCHAR(),
        nullable=True,
    )
    op.alter_column(
        "pending_github_oidc_publishers",
        "repository_owner",
        existing_type=sa.VARCHAR(),
        nullable=True,
    )
    op.alter_column(
        "pending_github_oidc_publishers",
        "repository_name",
        existing_type=sa.VARCHAR(),
        nullable=True,
    )
    op.alter_column(
        "github_oidc_publishers",
        "workflow_filename",
        existing_type=sa.VARCHAR(),
        nullable=True,
    )
    op.alter_column(
        "github_oidc_publishers",
        "repository_owner_id",
        existing_type=sa.VARCHAR(),
        nullable=True,
    )
    op.alter_column(
        "github_oidc_publishers",
        "repository_owner",
        existing_type=sa.VARCHAR(),
        nullable=True,
    )
    op.alter_column(
        "github_oidc_publishers",
        "repository_name",
        existing_type=sa.VARCHAR(),
        nullable=True,
    )
