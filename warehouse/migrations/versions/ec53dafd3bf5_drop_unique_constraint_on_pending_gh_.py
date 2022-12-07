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
drop unique constraint on pending GH providers

Revision ID: ec53dafd3bf5
Revises: 1d88dd9242e1
Create Date: 2022-12-06 20:11:54.617213
"""

from alembic import op

revision = "ec53dafd3bf5"
down_revision = "1d88dd9242e1"


def upgrade():
    op.drop_constraint(
        "_pending_github_oidc_provider_uc",
        "pending_github_oidc_providers",
        type_="unique",
    )


def downgrade():
    op.create_unique_constraint(
        "_pending_github_oidc_provider_uc",
        "pending_github_oidc_providers",
        ["repository_name", "repository_owner", "workflow_filename"],
    )
