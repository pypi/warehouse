# SPDX-License-Identifier: Apache-2.0
"""
Drop titan_promo_code table

Revision ID: 90f6ee9298db
Revises: d0f67adbcb80
Create Date: 2022-10-03 18:48:39.327937
"""

from alembic import op

revision = "90f6ee9298db"
down_revision = "d0f67adbcb80"


def upgrade():
    op.drop_index("ix_user_titan_codes_user_id", table_name="user_titan_codes")
    op.drop_table("user_titan_codes")


def downgrade():
    raise RuntimeError("Can't roll back")
