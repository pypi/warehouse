# SPDX-License-Identifier: Apache-2.0
"""
Add a flag for legacy file support

Revision ID: 3d2b8a42219a
Revises: 8c8be2c0e69e
Create Date: 2016-09-02 18:03:06.175231
"""

import sqlalchemy as sa

from alembic import op

revision = "3d2b8a42219a"
down_revision = "8c8be2c0e69e"


def upgrade():
    op.add_column(
        "packages", sa.Column("allow_legacy_files", sa.Boolean(), nullable=True)
    )

    op.execute("UPDATE packages SET allow_legacy_files = 't'")

    op.alter_column(
        "packages",
        "allow_legacy_files",
        nullable=False,
        server_default=sa.text("false"),
    )


def downgrade():
    op.drop_column("packages", "allow_legacy_files")
