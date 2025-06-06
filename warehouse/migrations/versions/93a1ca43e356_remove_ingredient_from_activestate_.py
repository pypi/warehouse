# SPDX-License-Identifier: Apache-2.0
"""
Remove 'ingredient' from ActiveState Publishing

Revision ID: 93a1ca43e356
Revises: 778f1c01a019
Create Date: 2024-03-13 16:13:44.417966
"""

import sqlalchemy as sa

from alembic import op

revision = "93a1ca43e356"
down_revision = "778f1c01a019"


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("activestate_oidc_publishers", "ingredient")
    op.drop_column("pending_activestate_oidc_publishers", "ingredient")
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "pending_activestate_oidc_publishers",
        sa.Column("ingredient", sa.VARCHAR(), autoincrement=False, nullable=True),
    )
    op.add_column(
        "activestate_oidc_publishers",
        sa.Column("ingredient", sa.VARCHAR(), autoincrement=False, nullable=True),
    )
    # ### end Alembic commands ###
