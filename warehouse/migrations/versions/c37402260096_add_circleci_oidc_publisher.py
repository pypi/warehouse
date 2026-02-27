# SPDX-License-Identifier: Apache-2.0
"""
Add CircleCI OIDC publisher

Revision ID: c37402260096
Revises: 28c1e0646708
Create Date: 2026-01-27 02:31:38.265440
"""

import sqlalchemy as sa

from alembic import op

revision = "c37402260096"
down_revision = "28c1e0646708"

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


def upgrade():
    op.create_table(
        "circleci_oidc_publishers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("circleci_org_id", sa.String(), nullable=False),
        sa.Column("circleci_project_id", sa.String(), nullable=False),
        sa.Column("pipeline_definition_id", sa.String(), nullable=False),
        sa.Column("context_id", sa.String(), nullable=True),
        sa.Column("vcs_ref", sa.String(), nullable=True),
        sa.Column("vcs_origin", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["id"],
            ["oidc_publishers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "circleci_org_id",
            "circleci_project_id",
            "pipeline_definition_id",
            "context_id",
            "vcs_ref",
            "vcs_origin",
            name="_circleci_oidc_publisher_uc",
        ),
    )
    op.create_table(
        "pending_circleci_oidc_publishers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("circleci_org_id", sa.String(), nullable=False),
        sa.Column("circleci_project_id", sa.String(), nullable=False),
        sa.Column("pipeline_definition_id", sa.String(), nullable=False),
        sa.Column("context_id", sa.String(), nullable=True),
        sa.Column("vcs_ref", sa.String(), nullable=True),
        sa.Column("vcs_origin", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["id"],
            ["pending_oidc_publishers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "circleci_org_id",
            "circleci_project_id",
            "pipeline_definition_id",
            "context_id",
            "vcs_ref",
            "vcs_origin",
            name="_pending_circleci_oidc_publisher_uc",
        ),
    )
    op.execute("""
        INSERT INTO admin_flags(id, description, enabled, notify)
        VALUES (
            'disallow-circleci-oidc',
            'Disallow the CircleCI OIDC provider',
            TRUE,
            FALSE
        )
        """)


def downgrade():
    op.drop_table("pending_circleci_oidc_publishers")
    op.drop_table("circleci_oidc_publishers")
    op.execute("DELETE FROM admin_flags WHERE id = 'disallow-circleci-oidc'")
