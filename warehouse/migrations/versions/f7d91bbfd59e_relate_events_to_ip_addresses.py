# SPDX-License-Identifier: Apache-2.0
"""
relate events to ip_addresses

Revision ID: f7d91bbfd59e
Revises: 2ee4c188adc2
Create Date: 2022-11-08 15:22:41.570355
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f7d91bbfd59e"
down_revision = "2ee4c188adc2"


def upgrade():
    # Organization events relation
    op.alter_column(
        "organization_events",
        "ip_address",
        new_column_name="ip_address_string",
        nullable=True,
    )
    op.add_column(
        "organization_events",
        sa.Column("ip_address_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        None,
        "organization_events",
        "ip_addresses",
        ["ip_address_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )

    # Project events relation
    op.alter_column(
        "project_events",
        "ip_address",
        new_column_name="ip_address_string",
        nullable=True,
    )
    op.add_column(
        "project_events",
        sa.Column("ip_address_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        None,
        "project_events",
        "ip_addresses",
        ["ip_address_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )

    # Team events relation
    op.alter_column(
        "team_events", "ip_address", new_column_name="ip_address_string", nullable=True
    )
    op.add_column(
        "team_events",
        sa.Column("ip_address_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        None,
        "team_events",
        "ip_addresses",
        ["ip_address_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )

    # User events relation
    op.alter_column(
        "user_events", "ip_address", new_column_name="ip_address_string", nullable=True
    )
    op.add_column(
        "user_events",
        sa.Column("ip_address_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        None,
        "user_events",
        "ip_addresses",
        ["ip_address_id"],
        ["id"],
        onupdate="CASCADE",
        ondelete="CASCADE",
    )


def downgrade():
    # User events
    op.drop_constraint(None, "user_events", type_="foreignkey")
    op.drop_column("user_events", "ip_address_id")
    op.alter_column(
        "user_events", "ip_address_string", new_column_name="ip_address", nullable=False
    )

    # Team events
    op.drop_constraint(None, "team_events", type_="foreignkey")
    op.drop_column("team_events", "ip_address_id")
    op.alter_column(
        "team_events", "ip_address_string", new_column_name="ip_address", nullable=False
    )

    # Project events
    op.drop_constraint(None, "project_events", type_="foreignkey")
    op.drop_column("project_events", "ip_address_id")
    op.alter_column(
        "project_events",
        "ip_address_string",
        new_column_name="ip_address",
        nullable=False,
    )

    # Organization events
    op.drop_constraint(None, "organization_events", type_="foreignkey")
    op.drop_column("organization_events", "ip_address_id")
    op.alter_column(
        "organization_events",
        "ip_address_string",
        new_column_name="ip_address",
        nullable=False,
    )
