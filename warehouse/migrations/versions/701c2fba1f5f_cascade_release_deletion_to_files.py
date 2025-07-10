# SPDX-License-Identifier: Apache-2.0
"""
Cascade Release deletion to Files

Revision ID: 701c2fba1f5f
Revises: b74a66a8f312
Create Date: 2018-03-09 23:06:05.382680
"""

from alembic import op

revision = "701c2fba1f5f"
down_revision = "b74a66a8f312"


def upgrade():
    op.execute(
        "ALTER TABLE release_files DROP CONSTRAINT IF EXISTS release_files_name_fkey"
    )
    op.create_foreign_key(
        "release_files_name_fkey",
        "release_files",
        "releases",
        ["name", "version"],
        ["name", "version"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint("release_files_name_fkey", "release_files", type_="foreignkey")
    op.create_foreign_key(
        "release_files_name_fkey",
        "release_files",
        "releases",
        ["name", "version"],
        ["name", "version"],
        onupdate="CASCADE",
    )
