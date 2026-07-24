# SPDX-License-Identifier: Apache-2.0
"""
Add project_create_ratelimit_string to organizations and users

Revision ID: 77d36f166ea1
Revises: 423ffda7411f
Create Date: 2026-07-24 11:00:10.303063
"""

import sqlalchemy as sa

from alembic import op

revision = "77d36f166ea1"
down_revision = "423ffda7411f"

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
        "organizations",
        sa.Column(
            "project_create_ratelimit_string",
            sa.String(),
            nullable=True,
            comment=(
                "Custom project-creation rate limit (e.g. '200 per hour') for "
                "this organization. Overrides the organization default when set."
            ),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "project_create_ratelimit_string",
            sa.String(),
            nullable=True,
            comment=(
                "Custom project-creation rate limit (e.g. '50 per hour') for "
                "this user. Overrides the global default when set."
            ),
        ),
    )


def downgrade():
    op.drop_column("users", "project_create_ratelimit_string")
    op.drop_column("organizations", "project_create_ratelimit_string")
