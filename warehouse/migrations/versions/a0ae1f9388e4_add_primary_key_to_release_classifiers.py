# SPDX-License-Identifier: Apache-2.0
"""
Add Primary Key to release_classifiers

Revision ID: a0ae1f9388e4
Revises: 7f6bed4f4345
Create Date: 2023-08-17 12:53:40.995825
"""

import sqlalchemy as sa

from alembic import op

revision = "a0ae1f9388e4"
down_revision = "7f6bed4f4345"


def upgrade():
    op.execute("SET statement_timeout = 61000")  # 61s
    op.execute("SET lock_timeout = 60000")  # 60s

    op.alter_column(
        "release_classifiers", "trove_id", existing_type=sa.INTEGER(), nullable=False
    )
    op.create_primary_key(
        "release_classifiers_pkey", "release_classifiers", ["trove_id", "release_id"]
    )


def downgrade():
    op.drop_constraint(
        "release_classifiers_pkey", "release_classifiers", type_="primary"
    )
    op.alter_column(
        "release_classifiers", "trove_id", existing_type=sa.INTEGER(), nullable=True
    )
