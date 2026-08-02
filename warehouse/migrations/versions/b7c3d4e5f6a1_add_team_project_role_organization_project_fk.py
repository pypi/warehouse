# SPDX-License-Identifier: Apache-2.0
"""
Add TeamProjectRole organization project FK

Revision ID: b7c3d4e5f6a1
Revises: 423ffda7411f
Create Date: 2026-08-02 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b7c3d4e5f6a1"
down_revision = "423ffda7411f"


def upgrade():
    op.add_column(
        "team_project_roles",
        sa.Column(
            "organization_project_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.execute("""
        UPDATE team_project_roles
        SET organization_project_id = organization_projects.id
        FROM teams, organization_projects
        WHERE team_project_roles.team_id = teams.id
            AND organization_projects.organization_id = teams.organization_id
            AND organization_projects.project_id = team_project_roles.project_id
    """)
    op.execute("""
        DELETE FROM team_project_roles
        WHERE organization_project_id IS NULL
    """)
    op.alter_column("team_project_roles", "organization_project_id", nullable=False)
    op.create_index(
        "team_project_roles_organization_project_id_idx",
        "team_project_roles",
        ["organization_project_id"],
        unique=False,
    )
    op.create_foreign_key(
        "team_project_roles_organization_project_id_fkey",
        "team_project_roles",
        "organization_projects",
        ["organization_project_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint(
        "team_project_roles_organization_project_id_fkey",
        "team_project_roles",
        type_="foreignkey",
    )
    op.drop_index(
        "team_project_roles_organization_project_id_idx",
        table_name="team_project_roles",
    )
    op.drop_column("team_project_roles", "organization_project_id")
