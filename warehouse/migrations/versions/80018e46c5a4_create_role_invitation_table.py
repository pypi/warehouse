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
create role invitation table

Revision ID: 80018e46c5a4
Revises: 87509f4ae027
Create Date: 2020-06-28 14:53:07.803972
"""
import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "80018e46c5a4"
down_revision = "87509f4ae027"


def upgrade():
    op.create_table(
        "role_invitations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("invite_status", sa.Text(), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "project_id", name="_role_invitations_user_project_uc"
        ),
    )
    op.create_index(
        "role_invitations_user_id_idx", "role_invitations", ["user_id"], unique=False
    )


def downgrade():
    op.drop_index("role_invitations_user_id_idx", table_name="role_invitations")
    op.drop_table("role_invitations")
