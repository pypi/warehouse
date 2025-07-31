# SPDX-License-Identifier: Apache-2.0
"""
Cascade Release deletion to Dependencies

Revision ID: c0302a8a0878
Revises: 701c2fba1f5f
Create Date: 2018-03-09 23:19:40.624047
"""

from alembic import op

revision = "c0302a8a0878"
down_revision = "701c2fba1f5f"


def upgrade():
    op.execute(
        "ALTER TABLE release_dependencies "
        "DROP CONSTRAINT IF EXISTS release_dependencies_name_fkey"
    )
    op.create_foreign_key(
        "release_dependencies_name_fkey",
        "release_dependencies",
        "releases",
        ["name", "version"],
        ["name", "version"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint(
        "release_dependencies_name_fkey", "release_dependencies", type_="foreignkey"
    )
    op.create_foreign_key(
        "release_dependencies_name_fkey",
        "release_dependencies",
        "releases",
        ["name", "version"],
        ["name", "version"],
        onupdate="CASCADE",
    )
