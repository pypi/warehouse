# SPDX-License-Identifier: Apache-2.0
"""
add squats table

Revision ID: eeb23d9b4d00
Revises: 56e9e630c748
Create Date: 2018-11-03 06:05:42.158355
"""

import sqlalchemy as sa

from alembic import op

revision = "eeb23d9b4d00"
down_revision = "56e9e630c748"


def upgrade():
    op.create_table(
        "warehouse_admin_squat",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("squatter_name", sa.Text(), nullable=True),
        sa.Column("squattee_name", sa.Text(), nullable=True),
        sa.Column(
            "reviewed", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["squattee_name"], ["packages.name"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["squatter_name"], ["packages.name"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("warehouse_admin_squat")
