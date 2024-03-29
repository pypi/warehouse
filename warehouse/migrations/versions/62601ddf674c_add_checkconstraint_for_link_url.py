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
Add CheckConstraint for link_url

Revision ID: 62601ddf674c
Revises: 1d88dd9242e1
Create Date: 2022-12-16 20:58:47.276985
"""

from alembic import op

revision = "62601ddf674c"
down_revision = "1d88dd9242e1"


def upgrade():
    op.create_check_constraint(
        "organizations_valid_link_url",
        "organizations",
        "link_url ~* '^https?://.*'::text",
    )


def downgrade():
    op.drop_constraint("organizations_valid_link_url", "organizations")
