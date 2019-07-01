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
Optimize Queries

Revision ID: 08447ab49999
Revises: 06bfbc92f67d
Create Date: 2018-11-10 20:37:11.391545
"""

from alembic import op

revision = "08447ab49999"
down_revision = "06bfbc92f67d"


def upgrade():
    op.create_index(
        op.f("ix_projects_sitemap_bucket"), "projects", ["sitemap_bucket"], unique=False
    )
    op.create_index(
        op.f("ix_users_sitemap_bucket"), "users", ["sitemap_bucket"], unique=False
    )
    op.create_index(
        "journakls_submitted_date_id_idx",
        "journals",
        ["submitted_date", "id"],
        unique=False,
    )
    op.create_index(op.f("ix_projects_created"), "projects", ["created"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_projects_created"), table_name="projects")
    op.drop_index("journakls_submitted_date_id_idx", table_name="journals")
    op.drop_index(op.f("ix_users_sitemap_bucket"), table_name="users")
    op.drop_index(op.f("ix_projects_sitemap_bucket"), table_name="projects")
