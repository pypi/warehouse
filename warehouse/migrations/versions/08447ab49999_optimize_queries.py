# SPDX-License-Identifier: Apache-2.0
"""
Optimize Queries

Revision ID: 08447ab49999
Revises: 06bfbc92f67d
Create Date: 2018-11-10 20:37:11.391545
"""

from alembic import op

revision = "08447ab49999"
down_revision = "06bfbc92f67d"


def upgrade():
    op.create_index(
        op.f("ix_projects_sitemap_bucket"), "projects", ["sitemap_bucket"], unique=False
    )
    op.create_index(
        op.f("ix_users_sitemap_bucket"), "users", ["sitemap_bucket"], unique=False
    )
    op.create_index(
        "journakls_submitted_date_id_idx",
        "journals",
        ["submitted_date", "id"],
        unique=False,
    )
    op.create_index(op.f("ix_projects_created"), "projects", ["created"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_projects_created"), table_name="projects")
    op.drop_index("journakls_submitted_date_id_idx", table_name="journals")
    op.drop_index(op.f("ix_users_sitemap_bucket"), table_name="users")
    op.drop_index(op.f("ix_projects_sitemap_bucket"), table_name="projects")
