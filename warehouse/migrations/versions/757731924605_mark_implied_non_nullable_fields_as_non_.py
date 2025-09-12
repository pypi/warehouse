# SPDX-License-Identifier: Apache-2.0
"""
Mark implied non-nullable fields as non-nullable

Revision ID: 757731924605
Revises: a0ae1f9388e4
Create Date: 2023-08-18 17:26:45.950001
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "757731924605"
down_revision = "a0ae1f9388e4"


def upgrade():
    op.execute("SET statement_timeout = 61000")  # 61s
    op.execute("SET lock_timeout = 60000")  # 60s

    op.alter_column(
        "release_files", "python_version", existing_type=sa.TEXT(), nullable=False
    )
    op.alter_column(
        "release_files",
        "packagetype",
        existing_type=postgresql.ENUM(
            "bdist_dmg",
            "bdist_dumb",
            "bdist_egg",
            "bdist_msi",
            "bdist_rpm",
            "bdist_wheel",
            "bdist_wininst",
            "sdist",
            name="package_type",
        ),
        nullable=False,
    )
    op.alter_column(
        "release_files", "filename", existing_type=sa.TEXT(), nullable=False
    )
    op.alter_column("release_files", "size", existing_type=sa.INTEGER(), nullable=False)
    op.alter_column(
        "release_files",
        "upload_time",
        existing_type=postgresql.TIMESTAMP(),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )


def downgrade():
    op.alter_column(
        "release_files",
        "upload_time",
        existing_type=postgresql.TIMESTAMP(),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column("release_files", "size", existing_type=sa.INTEGER(), nullable=True)
    op.alter_column("release_files", "filename", existing_type=sa.TEXT(), nullable=True)
    op.alter_column(
        "release_files",
        "packagetype",
        existing_type=postgresql.ENUM(
            "bdist_dmg",
            "bdist_dumb",
            "bdist_egg",
            "bdist_msi",
            "bdist_rpm",
            "bdist_wheel",
            "bdist_wininst",
            "sdist",
            name="package_type",
        ),
        nullable=True,
    )
    op.alter_column(
        "release_files", "python_version", existing_type=sa.TEXT(), nullable=True
    )
