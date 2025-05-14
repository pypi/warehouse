# SPDX-License-Identifier: Apache-2.0
"""
Cascade Project deletion to Release

Revision ID: 29d87a24d79e
Revises: c0682028c857
Create Date: 2018-03-09 22:37:21.343619
"""

from alembic import op

revision = "29d87a24d79e"
down_revision = "c0682028c857"


def upgrade():
    op.drop_constraint("releases_name_fkey", "releases", type_="foreignkey")
    op.create_foreign_key(
        "releases_name_fkey",
        "releases",
        "packages",
        ["name"],
        ["name"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint("releases_name_fkey", "releases", type_="foreignkey")
    op.create_foreign_key(
        "releases_name_fkey",
        "releases",
        "packages",
        ["name"],
        ["name"],
        onupdate="CASCADE",
    )
