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
webauthn model

Revision ID: af7dca2bb2fe
Revises: e1b493d3b171
Create Date: 2019-05-06 15:58:35.922060
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "af7dca2bb2fe"
down_revision = "e1b493d3b171"


def upgrade():
    op.create_table(
        "user_security_keys",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credential_id", sa.String, nullable=False),
        sa.Column("public_key", sa.String, nullable=True),
        sa.Column("sign_count", sa.Integer, nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], initially="DEFERRED", deferrable=True
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credential_id"),
        sa.UniqueConstraint("public_key"),
    )


def downgrade():
    op.drop_table("user_security_keys")
