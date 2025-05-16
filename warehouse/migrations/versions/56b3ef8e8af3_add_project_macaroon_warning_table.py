# SPDX-License-Identifier: Apache-2.0
"""
add_project_macaroon_warning_table

Revision ID: 56b3ef8e8af3
Revises: 8673550a67a3
Create Date: 2024-03-11 19:41:22.997939
"""

import sqlalchemy as sa

from alembic import op

revision = "56b3ef8e8af3"
down_revision = "8673550a67a3"


def upgrade():
    op.create_table(
        "project_macaroon_warning_association",
        sa.Column("macaroon_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["macaroon_id"],
            ["macaroons.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
        ),
        sa.PrimaryKeyConstraint("macaroon_id", "project_id", "id"),
    )


def downgrade():
    op.drop_table("project_macaroon_warning_association")
