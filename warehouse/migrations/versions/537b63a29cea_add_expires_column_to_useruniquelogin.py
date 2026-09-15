# SPDX-License-Identifier: Apache-2.0
"""
Add expires column to UserUniqueLogin

Revision ID: 537b63a29cea
Revises: 7cf64da2632a
Create Date: 2025-11-18 14:38:31.355587
"""

import sqlalchemy as sa

from alembic import op

from warehouse.utils.db.types import TZDateTime

revision = "537b63a29cea"
down_revision = "7cf64da2632a"


def upgrade():
    op.add_column(
        "user_unique_logins",
        sa.Column("expires", TZDateTime(), nullable=True),
    )

    op.execute("""
        UPDATE user_unique_logins
        SET expires =
            CASE
                WHEN status = 'confirmed' THEN NULL
                ELSE created + INTERVAL '6 hours'
            END
        """)


def downgrade():
    op.drop_column("user_unique_logins", "expires")
