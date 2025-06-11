# SPDX-License-Identifier: Apache-2.0
"""
Add missing indexes

Revision ID: 19ca1c78e613
Revises: 0e8f7729161a
Create Date: 2020-06-16 22:29:31.341596
"""

from alembic import op

revision = "19ca1c78e613"
down_revision = "0e8f7729161a"


def upgrade():
    op.create_index(
        op.f("ix_prohibited_project_names_prohibited_by"),
        "prohibited_project_names",
        ["prohibited_by"],
        unique=False,
    )
    op.drop_index("ix_blacklist_blacklisted_by", table_name="prohibited_project_names")


def downgrade():
    op.create_index(
        "ix_blacklist_blacklisted_by",
        "prohibited_project_names",
        ["prohibited_by"],
        unique=False,
    )
    op.drop_index(
        op.f("ix_prohibited_project_names_prohibited_by"),
        table_name="prohibited_project_names",
    )
