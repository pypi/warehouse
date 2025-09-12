# SPDX-License-Identifier: Apache-2.0
"""
Keep Observations when related removed

Revision ID: 444353e3eca2
Revises: c978a4eaa0f6
Create Date: 2024-04-18 15:29:53.793325
"""

import sqlalchemy as sa

from alembic import op

revision = "444353e3eca2"
down_revision = "c978a4eaa0f6"


def upgrade():
    op.alter_column(
        "project_observations",
        "related_id",
        existing_type=sa.UUID(),
        nullable=True,
        existing_comment="The ID of the related model",
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
    op.alter_column(
        "release_observations",
        "related_id",
        existing_type=sa.UUID(),
        nullable=True,
        existing_comment="The ID of the related model",
    )
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
        onupdate="CASCADE",
        ondelete="CASCADE",
    )
    op.alter_column(
        "release_observations",
        "related_id",
        existing_type=sa.UUID(),
        nullable=False,
        existing_comment="The ID of the related model",
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
        onupdate="CASCADE",
        ondelete="CASCADE",
    )
    op.alter_column(
        "project_observations",
        "related_id",
        existing_type=sa.UUID(),
        nullable=False,
        existing_comment="The ID of the related model",
    )
