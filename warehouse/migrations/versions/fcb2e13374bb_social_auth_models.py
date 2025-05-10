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
social auth models

Revision ID: fcb2e13374bb
Revises: c8384ca429fc
Create Date: 2025-04-27 16:01:36.308879
"""

import social_sqlalchemy
import sqlalchemy as sa

from alembic import op

revision = "fcb2e13374bb"
down_revision = "13c1c0ac92e9"


def upgrade():
    op.create_table(
        "social_auth_association",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("server_url", sa.String(length=255), nullable=True),
        sa.Column("handle", sa.String(length=255), nullable=True),
        sa.Column("secret", sa.String(length=255), nullable=True),
        sa.Column("issued", sa.Integer(), nullable=True),
        sa.Column("lifetime", sa.Integer(), nullable=True),
        sa.Column("assoc_type", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("server_url", "handle"),
    )
    op.create_table(
        "social_auth_code",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("code", sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", "email"),
    )
    op.create_index(
        op.f("ix_social_auth_code_code"), "social_auth_code", ["code"], unique=False
    )
    op.create_table(
        "social_auth_nonce",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("server_url", sa.String(length=255), nullable=True),
        sa.Column("timestamp", sa.Integer(), nullable=True),
        sa.Column("salt", sa.String(length=40), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("server_url", "timestamp", "salt"),
    )
    op.create_table(
        "social_auth_partial",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=32), nullable=True),
        sa.Column("data", social_sqlalchemy.storage.JSONType(), nullable=True),
        sa.Column("next_step", sa.Integer(), nullable=True),
        sa.Column("backend", sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_social_auth_partial_token"),
        "social_auth_partial",
        ["token"],
        unique=False,
    )
    op.create_table(
        "social_auth_usersocialauth",
        sa.Column("uid", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("extra_data", social_sqlalchemy.storage.JSONType(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "uid"),
    )
    op.create_index(
        op.f("ix_social_auth_usersocialauth_user_id"),
        "social_auth_usersocialauth",
        ["user_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_social_auth_usersocialauth_user_id"),
        table_name="social_auth_usersocialauth",
    )
    op.drop_table("social_auth_usersocialauth")
    op.drop_index(
        op.f("ix_social_auth_partial_token"), table_name="social_auth_partial"
    )
    op.drop_table("social_auth_partial")
    op.drop_table("social_auth_nonce")
    op.drop_index(op.f("ix_social_auth_code_code"), table_name="social_auth_code")
    op.drop_table("social_auth_code")
    op.drop_table("social_auth_association")
