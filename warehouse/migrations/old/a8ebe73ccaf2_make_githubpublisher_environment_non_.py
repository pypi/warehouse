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
Make GitHubPublisher environment non-nullable

Revision ID: a8ebe73ccaf2
Revises: a2af745511e0
Create Date: 2023-08-16 19:48:03.178852
"""

import sqlalchemy as sa

from alembic import op

revision = "a8ebe73ccaf2"
down_revision = "a2af745511e0"


def upgrade():
    # Data migration
    op.execute(
        "UPDATE github_oidc_publishers SET environment = '' where environment IS NULL"
    )
    op.execute(
        "UPDATE pending_github_oidc_publishers "
        "SET environment = '' where environment IS NULL"
    )

    op.alter_column(
        "github_oidc_publishers",
        "environment",
        existing_type=sa.VARCHAR(),
        nullable=False,
    )
    op.alter_column(
        "pending_github_oidc_publishers",
        "environment",
        existing_type=sa.VARCHAR(),
        nullable=False,
    )


def downgrade():
    op.alter_column(
        "pending_github_oidc_publishers",
        "environment",
        existing_type=sa.VARCHAR(),
        nullable=True,
    )
    op.alter_column(
        "github_oidc_publishers",
        "environment",
        existing_type=sa.VARCHAR(),
        nullable=True,
    )

    # Data migration
    op.execute(
        "UPDATE github_oidc_publishers SET environment = NULL where environment = ''"
    )
    op.execute(
        "UPDATE pending_github_oidc_publishers "
        "SET environment = NULL where environment = ''"
    )
