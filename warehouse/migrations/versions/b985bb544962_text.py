# SPDX-License-Identifier: Apache-2.0
"""
Rename package_type enum to packagetype

Revision ID: b985bb544962
Revises: 757731924605
Create Date: 2023-09-08 18:06:56.085062
"""

from alembic import op

revision = "b985bb544962"
down_revision = "757731924605"


def upgrade():
    op.execute("ALTER TYPE package_type RENAME TO packagetype")


def downgrade():
    op.execute("ALTER TYPE packagetype RENAME TO package_type ")
