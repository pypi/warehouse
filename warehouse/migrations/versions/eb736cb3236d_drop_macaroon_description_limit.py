# SPDX-License-Identifier: Apache-2.0
"""
Drop Macaroon description limit

Revision ID: eb736cb3236d
Revises: cc06bd67a61b
Create Date: 2023-03-07 21:29:53.314390
"""

import sqlalchemy as sa

from alembic import op

revision = "eb736cb3236d"
down_revision = "cc06bd67a61b"


def upgrade():
    op.alter_column(
        "macaroons",
        "description",
        existing_type=sa.VARCHAR(length=100),
        type_=sa.String(),
        existing_nullable=False,
    )


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
