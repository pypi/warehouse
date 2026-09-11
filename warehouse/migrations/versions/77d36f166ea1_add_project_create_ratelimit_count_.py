# SPDX-License-Identifier: Apache-2.0
"""
Add project_create_ratelimit_count/period to organizations and users

Revision ID: 77d36f166ea1
Revises: 964076d0c4ad
Create Date: 2026-07-24 11:00:10.303063
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "77d36f166ea1"
down_revision = "964076d0c4ad"

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

# Nullable with no default: catalog-only ADD COLUMN, no rewrite of users.

COUNT_COMMENT = (
    "Project creation rate limit count, e.g. the 20 in '20 per hour'. "
    "NULL means no override: the configured default applies."
)
PERIOD_COMMENT = (
    "Period the count is measured over. Must be NULL exactly when "
    "project_create_ratelimit_count is NULL."
)
PERIODS = ("hour", "day", "month")


def upgrade():
    sa.Enum(*PERIODS, name="ratelimitperiod").create(op.get_bind())

    for table in ("organizations", "users"):
        op.add_column(
            table,
            sa.Column(
                "project_create_ratelimit_count",
                sa.Integer(),
                nullable=True,
                comment=COUNT_COMMENT,
            ),
        )
        op.add_column(
            table,
            sa.Column(
                "project_create_ratelimit_period",
                postgresql.ENUM(*PERIODS, name="ratelimitperiod", create_type=False),
                nullable=True,
                comment=PERIOD_COMMENT,
            ),
        )
        op.create_check_constraint(
            f"{table}_project_create_ratelimit_complete",
            table,
            "(project_create_ratelimit_count IS NULL) = "
            "(project_create_ratelimit_period IS NULL)",
        )


def downgrade():
    for table in ("users", "organizations"):
        op.drop_constraint(
            f"{table}_project_create_ratelimit_complete", table, type_="check"
        )
    op.drop_column("users", "project_create_ratelimit_period")
    op.drop_column("users", "project_create_ratelimit_count")
    op.drop_column("organizations", "project_create_ratelimit_period")
    op.drop_column("organizations", "project_create_ratelimit_count")
    sa.Enum(name="ratelimitperiod").drop(op.get_bind())
