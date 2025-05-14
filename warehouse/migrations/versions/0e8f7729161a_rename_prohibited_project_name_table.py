# SPDX-License-Identifier: Apache-2.0
"""
Rename table for prohibited project names.

Revision ID: 0e8f7729161a
Revises: 30a7791fea33
Create Date: 2020-06-02 16:16:21.043443
"""

from alembic import op

revision = "0e8f7729161a"
down_revision = "30a7791fea33"


def upgrade():
    op.alter_column("blacklist", "blacklisted_by", new_column_name="prohibited_by")
    op.rename_table("blacklist", "prohibited_project_names")


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
