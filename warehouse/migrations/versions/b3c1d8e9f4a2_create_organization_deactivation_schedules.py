# SPDX-License-Identifier: Apache-2.0
"""
create organization deactivation schedules

Revision ID: b3c1d8e9f4a2
Revises: f555f02f7688
Create Date: 2026-10-17 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "b3c1d8e9f4a2"
down_revision = "f555f02f7688"

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
        "organization_deactivation_schedules",
        sa.Column(
            "organization_id",
            sa.UUID(),
            nullable=False,
            comment="Foreign key to organization",
        ),
        sa.Column(
            "created",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Datetime when the deactivation notice period started",
        ),
        sa.Column(
            "deactivate_on",
            sa.Date(),
            nullable=False,
            comment="Date (UTC) on or after which the organization is deactivated",
        ),
        sa.Column(
            "last_notice_days",
            sa.Integer(),
            nullable=False,
            comment="Days-before-deactivation of the most recent notice sent",
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("organization_id"),
    )
    op.execute("""
        INSERT INTO admin_flags(id, description, enabled, notify)
        VALUES (
            'disallow-organization-deactivation',
            'Pause unpaid org deactivations and their emails',
            FALSE,
            FALSE
        )
    """)


def downgrade():
    op.execute(
        "DELETE FROM admin_flags WHERE id = 'disallow-organization-deactivation'"
    )
    op.drop_table("organization_deactivation_schedules")
