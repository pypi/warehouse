# SPDX-License-Identifier: Apache-2.0
"""
Add Observation.related_name

Revision ID: c978a4eaa0f6
Revises: 8673550a67a3
Create Date: 2024-04-15 19:16:58.787722
"""

import sqlalchemy as sa

from alembic import op

# from warehouse.packaging.models import Project

revision = "c978a4eaa0f6"
down_revision = "56b3ef8e8af3"

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
    op.add_column(
        "project_observations",
        sa.Column(
            "related_name",
            sa.String(),
            nullable=True,  # we will flip this later
            comment="The name of the related model",
        ),
    )

    # NOTE: Commenting out the following to avoid failing other migrations during tests.
    # Migration ran successfully in production on 2024-04-17

    # Data migration to set the related_name for existing rows.
    # bind = op.get_bind()
    # session = sa.orm.Session(bind=bind)
    # # Get all Projects with Observations
    # projects_query = sa.select(Project).where(Project.observations.any())
    # # For each, set the `related_name` to the related Project's model name
    # for project in session.scalars(projects_query):
    #     for observation in project.observations:
    #         observation.related_name = repr(project)
    #         session.add(observation)
    # session.commit()

    # Flip the nullable flag to False
    op.alter_column("project_observations", "related_name", nullable=False)

    # We don't have any records in the release_observations table yet, so we can
    # just add the column with the correct nullable flag.
    op.add_column(
        "release_observations",
        sa.Column(
            "related_name",
            sa.String(),
            nullable=False,
            comment="The name of the related model",
        ),
    )


def downgrade():
    op.drop_column("release_observations", "related_name")
    op.drop_column("project_observations", "related_name")
