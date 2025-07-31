# SPDX-License-Identifier: Apache-2.0
"""
Make File.path mandatory

Revision ID: f46672a776f1
Revises: 6ff880c36cd9
Create Date: 2016-01-07 13:17:25.942208
"""

from alembic import op

revision = "f46672a776f1"
down_revision = "6ff880c36cd9"


def upgrade():
    op.execute(
        """ UPDATE release_files
               SET path = concat_ws(
                            '/',
                            python_version,
                            substring(name, 1, 1),
                            name,
                            filename
                          )
             WHERE path IS NULL
        """
    )
    op.alter_column("release_files", "path", nullable=False)


def downgrade():
    op.alter_column("release_files", "path", nullable=True)
