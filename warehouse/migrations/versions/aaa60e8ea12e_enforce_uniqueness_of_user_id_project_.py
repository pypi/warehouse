# SPDX-License-Identifier: Apache-2.0
"""
enforce uniqueness of user_id, project_id on roles

Revision ID: aaa60e8ea12e
Revises: 5c029d9ef925
Create Date: 2020-03-04 21:56:32.651065
"""

from alembic import op

revision = "aaa60e8ea12e"
down_revision = "5c029d9ef925"


def upgrade():
    op.execute("""
        DELETE FROM roles
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                ROW_NUMBER() OVER (
                    PARTITION BY project_id, user_id ORDER BY role_name DESC
                ) as row_num
                FROM roles
            ) t
            WHERE t.row_num > 1
        )
        RETURNING *
        """)
    op.create_unique_constraint(
        "_roles_user_project_uc", "roles", ["user_id", "project_id"]
    )


def downgrade():
    op.drop_constraint("_roles_user_project_uc", "roles", type_="unique")
