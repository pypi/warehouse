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
rename GitHubProvider fields

Revision ID: bb986a64761a
Revises: 9f0f99509d92
Create Date: 2022-04-22 22:00:53.832695
"""

from alembic import op

revision = "bb986a64761a"
down_revision = "9f0f99509d92"


def upgrade():
    op.drop_constraint(
        "_github_oidc_provider_uc", "github_oidc_providers", type_="unique"
    )
    op.alter_column(
        "github_oidc_providers", "owner_id", new_column_name="repository_owner_id"
    )
    op.alter_column(
        "github_oidc_providers", "owner", new_column_name="repository_owner"
    )
    op.create_unique_constraint(
        "_github_oidc_provider_uc",
        "github_oidc_providers",
        ["repository_name", "repository_owner", "workflow_filename"],
    )


def downgrade():
    op.drop_constraint(
        "_github_oidc_provider_uc", "github_oidc_providers", type_="unique"
    )
    op.alter_column(
        "github_oidc_providers", "repository_owner_id", new_column_name="owner_id"
    )
    op.alter_column(
        "github_oidc_providers", "repository_owner", new_column_name="owner"
    )
    op.create_unique_constraint(
        "_github_oidc_provider_uc",
        "github_oidc_providers",
        ["repository_name", "owner", "workflow_filename"],
    )
