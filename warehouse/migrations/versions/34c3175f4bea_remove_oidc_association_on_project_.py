# SPDX-License-Identifier: Apache-2.0
"""
Remove OIDC Association on Project Delete

Revision ID: 34c3175f4bea
Revises: 1fdecaf73541
Create Date: 2024-04-09 21:38:26.340992
"""

from alembic import op

revision = "34c3175f4bea"
down_revision = "1fdecaf73541"


def upgrade():
    op.drop_constraint(
        "oidc_publisher_project_association_project_id_fkey",
        "oidc_publisher_project_association",
        type_="foreignkey",
    )
    op.create_foreign_key(
        None,
        "oidc_publisher_project_association",
        "projects",
        ["project_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint(None, "oidc_publisher_project_association", type_="foreignkey")
    op.create_foreign_key(
        "oidc_publisher_project_association_project_id_fkey",
        "oidc_publisher_project_association",
        "projects",
        ["project_id"],
        ["id"],
    )
