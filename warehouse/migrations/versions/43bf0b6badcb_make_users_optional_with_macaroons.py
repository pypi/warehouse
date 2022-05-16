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
Make users optional with Macaroons

Revision ID: 43bf0b6badcb
Revises: 6e003184453d
Create Date: 2022-04-19 14:57:54.765006
"""

import sqlalchemy as sa

from alembic import op
from citext import CIText
from sqlalchemy.dialects import postgresql

revision = "43bf0b6badcb"
down_revision = "6e003184453d"


def upgrade():
    # Macaroon users are now optional.
    op.alter_column(
        "macaroons", "user_id", existing_type=postgresql.UUID(), nullable=True
    )

    # JournalEvent users are now optional.
    op.alter_column("journals", "submitted_by", existing_type=CIText(), nullable=True)

    # Macaroons might have an associated project (if not user-associated).
    op.add_column(
        "macaroons",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_unique_constraint(
        "_project_macaroons_description_uc", "macaroons", ["description", "project_id"]
    )
    op.create_index(
        op.f("ix_macaroons_project_id"), "macaroons", ["project_id"], unique=False
    )
    op.create_foreign_key(None, "macaroons", "projects", ["project_id"], ["id"])

    # Macaroon -> (User XOR Project)
    op.create_check_constraint(
        "_user_xor_project_macaroon",
        table_name="macaroons",
        condition="(user_id::text IS NULL) <> (project_id::text IS NULL)",
    )


def downgrade():
    op.alter_column(
        "macaroons", "user_id", existing_type=postgresql.UUID(), nullable=False
    )

    op.alter_column("journals", "submitted_by", existing_type=CIText(), nullable=False)

    op.drop_constraint(None, "macaroons", type_="foreignkey")
    op.drop_index(op.f("ix_macaroons_project_id"), table_name="macaroons")
    op.drop_constraint("_project_macaroons_description_uc", "macaroons", type_="unique")
    op.drop_column("macaroons", "project_id")

    op.drop_constraint("_user_xor_project_macaroon")
