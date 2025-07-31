# SPDX-License-Identifier: Apache-2.0
"""
create index on roles table for project_id

Revision ID: b6d057388dd9
Revises: 80018e46c5a4
Create Date: 2020-11-09 17:13:40.639721
"""

from alembic import op

revision = "b6d057388dd9"
down_revision = "80018e46c5a4"


def upgrade():
    op.create_index("roles_project_id_idx", "roles", ["project_id"], unique=False)


def downgrade():
    op.drop_index("roles_project_id_idx", table_name="roles")
