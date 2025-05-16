# SPDX-License-Identifier: Apache-2.0
"""
create table for warehouse administration flags

Revision ID: 7165e957cddc
Revises: 1e2ccd34f539
Create Date: 2018-02-17 18:42:18.209572
"""

import sqlalchemy as sa

from alembic import op

revision = "7165e957cddc"
down_revision = "1e2ccd34f539"


def upgrade():
    op.create_table(
        "warehouse_admin_flag",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # Insert our initial flags.
    op.execute(
        """
        INSERT INTO warehouse_admin_flag(id, description, enabled)
        VALUES (
            'disallow-new-user-registration',
            'Disallow ALL new User registrations',
            FALSE
        )
    """
    )
    op.execute(
        """
        INSERT INTO warehouse_admin_flag(id, description, enabled)
        VALUES (
            'disallow-new-project-registration',
            'Disallow ALL new Project registrations',
            FALSE
        )
    """
    )


def downgrade():
    op.drop_table("warehouse_admin_flag")
