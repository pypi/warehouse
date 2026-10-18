# SPDX-License-Identifier: Apache-2.0
"""
add organization deactivation

Revision ID: b3c1d8e9f4a2
Revises: f555f02f7688
Create Date: 2026-10-17 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

from warehouse.utils.db.types import TZDateTime

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
    sa.Enum(
        "no_paid_seat", "owner_removed", name="organizationdeactivationreason"
    ).create(op.get_bind())
    op.add_column(
        "organizations",
        sa.Column(
            "deactivated",
            TZDateTime(),
            nullable=True,
            comment="Datetime the organization was deactivated. NULL while active.",
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "deactivated_reason",
            postgresql.ENUM(
                "no_paid_seat",
                "owner_removed",
                name="organizationdeactivationreason",
                create_type=False,
            ),
            nullable=True,
            comment="Why the organization was deactivated, if known.",
        ),
    )
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
            comment="Last day (UTC) to purchase a seat before deactivation",
        ),
        sa.Column(
            "last_notice_days",
            sa.Integer(),
            nullable=False,
            comment="Days-before-deactivation of the most recent notice",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("organization_id"),
    )
    op.create_table(
        "organization_deactivation_notices",
        sa.Column(
            "organization_id",
            sa.UUID(),
            nullable=False,
            comment="Foreign key to organization",
        ),
        sa.Column(
            "deactivated",
            sa.Boolean(),
            nullable=False,
            comment="True if the org was deactivated, False for a reminder",
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_organization_deactivation_notices_organization_id"),
        "organization_deactivation_notices",
        ["organization_id"],
        unique=False,
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
    op.drop_index(
        op.f("ix_organization_deactivation_notices_organization_id"),
        table_name="organization_deactivation_notices",
    )
    op.drop_table("organization_deactivation_notices")
    op.drop_table("organization_deactivation_schedules")
    op.drop_column("organizations", "deactivated_reason")
    op.drop_column("organizations", "deactivated")
    sa.Enum(
        "no_paid_seat", "owner_removed", name="organizationdeactivationreason"
    ).drop(op.get_bind())
