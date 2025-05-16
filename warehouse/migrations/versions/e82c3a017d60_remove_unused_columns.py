# SPDX-License-Identifier: Apache-2.0
"""
Remove unused columns

Revision ID: e82c3a017d60
Revises: 62f6becc7653
Create Date: 2018-08-17 16:23:08.775818
"""

from alembic import op

revision = "e82c3a017d60"
down_revision = "62f6becc7653"


def upgrade():
    op.drop_column("accounts_user", "is_staff")
    op.drop_column("packages", "hosting_mode")
    op.drop_column("packages", "autohide")
    op.drop_column("packages", "bugtrack_url")
    op.drop_column("packages", "comments")
    op.drop_column("packages", "stable_version")
    op.drop_column("release_files", "downloads")
    op.drop_column("releases", "description_from_readme")
    op.drop_column("releases", "_pypi_hidden")


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
