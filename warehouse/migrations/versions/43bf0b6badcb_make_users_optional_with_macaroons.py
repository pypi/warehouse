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
Revises: ef0a77c48089
Create Date: 2022-04-19 14:57:54.765006
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "43bf0b6badcb"
down_revision = "ef0a77c48089"


def upgrade():
    # Macaroon users are now optional.
    op.alter_column(
        "macaroons", "user_id", existing_type=postgresql.UUID(), nullable=True
    )

    # Macaroons might have an associated OIDCProvider (if not user-associated).
    op.add_column(
        "macaroons",
        sa.Column("oidc_provider_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        op.f("ix_macaroons_oidc_provider_id"),
        "macaroons",
        ["oidc_provider_id"],
        unique=False,
    )
    op.create_foreign_key(
        None, "macaroons", "oidc_providers", ["oidc_provider_id"], ["id"]
    )

    # JournalEvent users are now optional.
    op.alter_column(
        "journals", "submitted_by", existing_type=postgresql.CITEXT(), nullable=True
    )

    # Macaroon -> (User XOR OIDCProvider)
    op.create_check_constraint(
        "_user_xor_oidc_provider_macaroon",
        table_name="macaroons",
        condition="(user_id::text IS NULL) <> (oidc_provider_id::text IS NULL)",
    )


def downgrade():
    op.alter_column(
        "macaroons", "user_id", existing_type=postgresql.UUID(), nullable=False
    )

    op.alter_column(
        "journals", "submitted_by", existing_type=postgresql.CITEXT(), nullable=False
    )
