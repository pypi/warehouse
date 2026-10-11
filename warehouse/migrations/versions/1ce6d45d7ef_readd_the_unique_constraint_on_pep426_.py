# SPDX-License-Identifier: Apache-2.0
"""
re-add the unique constraint on pep426 normalization

Revision ID: 1ce6d45d7ef
Revises: 23a3c4ffe5d
Create Date: 2015-06-04 23:09:11.612200
"""

from alembic import op

revision = "1ce6d45d7ef"
down_revision = "23a3c4ffe5d"


def upgrade():
    op.execute(""" CREATE UNIQUE INDEX project_name_pep426_normalized
            ON packages
            (normalize_pep426_name(name))
        """)


def downgrade():
    op.execute("DROP INDEX project_name_pep426_normalized")
