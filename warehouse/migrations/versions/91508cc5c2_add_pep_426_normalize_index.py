# SPDX-License-Identifier: Apache-2.0
"""
Add Index for normalized PEP 426 names which enforces uniqueness.

Revision ID: 91508cc5c2
Revises: 20f4dbe11e9
Create Date: 2015-04-04 23:55:27.024988
"""

from alembic import op

revision = "91508cc5c2"
down_revision = "20f4dbe11e9"


def upgrade():
    op.execute("""
        CREATE UNIQUE INDEX project_name_pep426_normalized
            ON packages
            (normalize_pep426_name(name))
    """)


def downgrade():
    op.execute("DROP INDEX project_name_pep426_normalized")
