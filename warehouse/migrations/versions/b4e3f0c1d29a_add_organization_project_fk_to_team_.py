# SPDX-License-Identifier: Apache-2.0
"""
Add organization_project_id FK to team_project_roles

Revision ID: b4e3f0c1d29a
Revises: 77d36f166ea1
Create Date: 2026-09-15 10:42:18.117204
"""

import sqlalchemy as sa

from alembic import op

revision = "b4e3f0c1d29a"
down_revision = "77d36f166ea1"

# Note: It is VERY important to ensure that a migration does not lock for a
#       long period of time and to ensure that each individual migration does
#       not break compatibility with the *previous* version of the code base.
#       This is because the migrations will be ran automatically as part of the
#       deployment process, but while the previous version of the code is still
#       up and running. Thus backwards incompatible changes must be broken up
#       over multiple migrations inside of multiple pull requests in order to
#       phase them in over multiple deploys.
#
#       By default, migrations cannot wait more than 4s on acquiring a lock
#       and each individual statement cannot take more than 5s. This helps
#       prevent situations where a slow migration takes the entire site down.
#
#       If you need to increase this timeout for a migration, you can do so
#       by adding:
#
#           op.execute("SET statement_timeout = 5000")
#           op.execute("SET lock_timeout = 4000")
#
#       To whatever values are reasonable for this migration as part of your
#       migration.

# Phase 1 of 2. The column is added nullable so that the previous version of
# the code -- which inserts TeamProjectRole rows without it -- keeps working
# while this migration is applied. A follow-up migration sets NOT NULL once
# every writer populates the column and any remaining orphans are resolved.
# See https://github.com/pypi/warehouse/issues/19748

COLUMN_COMMENT = (
    "The org-project association this role depends on. Lets the database "
    "cascade the role away when a project leaves the organization. NULL only "
    "for rows predating this column."
)

# Existing roles are matched to their association by joining a team to its
# organization, then that organization to the project the role grants access
# to. Rows with no match are grants that outlived their org-project link --
# they are left NULL here and dealt with in the follow-up migration, so that
# this one performs no destructive writes against production data.
BACKFILL = """
    UPDATE team_project_roles AS tpr
    SET organization_project_id = op.id
    FROM teams AS t
    JOIN organization_projects AS op
      ON op.organization_id = t.organization_id
    WHERE tpr.team_id = t.id
      AND op.project_id = tpr.project_id
      AND tpr.organization_project_id IS NULL
"""


def upgrade():
    # Nullable with no default: catalog-only ADD COLUMN, no table rewrite.
    op.add_column(
        "team_project_roles",
        sa.Column(
            "organization_project_id",
            sa.UUID(as_uuid=True),
            nullable=True,
            comment=COLUMN_COMMENT,
        ),
    )

    op.execute(BACKFILL)

    op.create_index(
        "team_project_roles_organization_project_id_idx",
        "team_project_roles",
        ["organization_project_id"],
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
