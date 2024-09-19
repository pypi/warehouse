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
add project alternate repositories table

Revision ID: a8050411bc65
Revises:
Create Date: 2024-04-25 00:26:09.199573
"""

import sqlalchemy as sa

from alembic import op

revision = "a8050411bc65"
down_revision = "0b74ed7d4880"


def upgrade():
    op.create_table(
        "alternate_repositories",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.CheckConstraint(
            "url ~* '^https?://.+'::text", name="alternate_repository_valid_url"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name"),
        sa.UniqueConstraint("project_id", "url"),
    )


def downgrade():
    op.drop_table("alternate_repositories")
