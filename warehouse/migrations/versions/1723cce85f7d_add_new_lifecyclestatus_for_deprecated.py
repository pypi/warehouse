# SPDX-License-Identifier: Apache-2.0
"""
Add new LifecycleStatus for Deprecated

Revision ID: 1723cce85f7d
Revises: 3aded0448fe7
Create Date: 2026-11-21 15:21:08.796429
"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "1723cce85f7d"
down_revision = "3aded0448fe7"

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
    op.add_enum_value(
        enum_schema="public",
        enum_name="lifecyclestatus",
        new_value="deprecated",
    )


def downgrade():
    op.sync_enum_values(
        enum_schema="public",
        enum_name="lifecyclestatus",
        new_values=[
            "quarantine-enter",
            "quarantine-exit",
            "archived",
            "archived-noindex",
        ],
        affected_columns=[
            TableReference(
                table_schema="public",
                table_name="projects",
                column_name="lifecycle_status",
            ),
            TableReference(
                table_schema="public",
                table_name="releases",
                column_name="lifecycle_status",
            ),
        ],
        enum_values_to_rename=[],
    )
