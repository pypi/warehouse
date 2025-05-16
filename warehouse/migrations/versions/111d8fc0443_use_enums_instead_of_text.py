# SPDX-License-Identifier: Apache-2.0
"""
Use enums instead of text

Revision ID: 111d8fc0443
Revises: 5988e3e8d2e
Create Date: 2015-03-08 22:46:46.870190
"""

from alembic import op
from sqlalchemy.dialects.postgresql import ENUM

revision = "111d8fc0443"
down_revision = "5988e3e8d2e"


def upgrade():
    package_type = ENUM(
        "bdist_dmg",
        "bdist_dumb",
        "bdist_egg",
        "bdist_msi",
        "bdist_rpm",
        "bdist_wheel",
        "bdist_wininst",
        "sdist",
        name="package_type",
        create_type=False,
    )
    package_type.create(op.get_bind(), checkfirst=False)

    op.execute(
        """ ALTER TABLE release_files
                ALTER COLUMN packagetype
                TYPE package_type
                USING packagetype::package_type
        """
    )


def downgrade():
    op.execute(
        """ ALTER TABLE release_files
                ALTER COLUMN packagetype
                TYPE text
        """
    )

    ENUM(name="package_type", create_type=False).drop(op.get_bind(), checkfirst=False)
