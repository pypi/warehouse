# SPDX-License-Identifier: Apache-2.0
"""
cascade observation delete

Revision ID: 812e14a4cddf
Revises: a073e7979805
Create Date: 2024-01-18 18:46:58.482270
"""

from alembic import op

revision = "812e14a4cddf"
down_revision = "9a0ed2044b53"


def upgrade():
    op.drop_constraint(
        "project_observations_related_id_fkey",
        "project_observations",
        type_="foreignkey",
    )
    op.create_foreign_key(
        None,
        "project_observations",
        "projects",
        ["related_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "release_observations_related_id_fkey",
        "release_observations",
        type_="foreignkey",
    )
    op.create_foreign_key(
        None,
        "release_observations",
        "releases",
        ["related_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint(
        "release_observations_related_id_fkey",
        "release_observations",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "release_observations_related_id_fkey",
        "release_observations",
        "releases",
        ["related_id"],
        ["id"],
    )
    op.drop_constraint(
        "project_observations_related_id_fkey",
        "project_observations",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "project_observations_related_id_fkey",
        "project_observations",
        "projects",
        ["related_id"],
        ["id"],
    )
