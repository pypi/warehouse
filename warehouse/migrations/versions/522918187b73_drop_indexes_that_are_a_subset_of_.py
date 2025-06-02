# SPDX-License-Identifier: Apache-2.0
"""
Drop indexes that are a subset of another index

Revision ID: 522918187b73
Revises: 0864352e2168
Create Date: 2018-08-17 07:05:14.667760
"""

from alembic import op

revision = "522918187b73"
down_revision = "0864352e2168"


def upgrade():
    op.drop_index("rel_dep_name_version_idx", table_name="release_dependencies")
    op.drop_index("release_name_idx", table_name="releases")


def downgrade():
    op.create_index("release_name_idx", "releases", ["name"], unique=False)
    op.create_index(
        "rel_dep_name_version_idx",
        "release_dependencies",
        ["name", "version"],
        unique=False,
    )
