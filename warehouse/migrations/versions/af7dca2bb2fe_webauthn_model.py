# SPDX-License-Identifier: Apache-2.0
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
