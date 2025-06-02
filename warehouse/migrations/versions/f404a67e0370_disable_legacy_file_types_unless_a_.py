# SPDX-License-Identifier: Apache-2.0
"""
Disable legacy file types unless a project has used them previously

Revision ID: f404a67e0370
Revises: b8fda0d7fbb5
Create Date: 2016-12-17 02:58:55.328035
"""

from alembic import op

revision = "f404a67e0370"
down_revision = "b8fda0d7fbb5"


def upgrade():
    op.execute(
        r""" UPDATE packages
            SET allow_legacy_files = 'f'
            WHERE name NOT IN (
                SELECT DISTINCT ON (packages.name) packages.name
                FROM packages, release_files
                WHERE packages.name = release_files.name
                    AND (
                        filename !~* '.+?\.(tar\.gz|zip|whl|egg)$'
                        OR packagetype NOT IN (
                            'sdist',
                            'bdist_wheel',
                            'bdist_egg'
                        )
                    )
            )
        """
    )


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
