# SPDX-License-Identifier: Apache-2.0
"""
Remove the rego_otk table abd related index

Revision ID: 42e76a605cac
Revises: 895279cc4490
Create Date: 2018-08-03 23:45:11.301066
"""

from alembic import op

revision = "42e76a605cac"
down_revision = "895279cc4490"


def upgrade():
    op.drop_index("rego_otk_name_idx", table_name="rego_otk")
    op.drop_index("rego_otk_otk_idx", table_name="rego_otk")
    op.drop_table("rego_otk")


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
