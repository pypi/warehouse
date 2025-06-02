# SPDX-License-Identifier: Apache-2.0
"""
Index ultranormalized pending project_name

Revision ID: f7720656a33c
Revises: 6ee23f5a6c1b
Create Date: 2024-08-20 06:07:46.546659
"""

from alembic import op

revision = "f7720656a33c"
down_revision = "6ee23f5a6c1b"

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
    op.execute(
        """
        CREATE INDEX pending_project_name_ultranormalized
          ON pending_oidc_publishers (ultranormalize_name(project_name));
        """
    )


def downgrade():
    op.execute("DROP INDEX pending_project_name_ultranormalized")
