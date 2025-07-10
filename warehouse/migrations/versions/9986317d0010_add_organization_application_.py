# SPDX-License-Identifier: Apache-2.0
"""
add organization application observations

Revision ID: 9986317d0010
Revises: e1b0e2c4a1e6
Create Date: 2025-03-13 20:40:09.890450
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "9986317d0010"
down_revision = "e1b0e2c4a1e6"


def upgrade():
    op.create_table(
        "organizationapplication_observations",
        sa.Column(
            "related_id",
            sa.UUID(),
            nullable=True,
            comment="The ID of the related model",
        ),
        sa.Column(
            "related_name",
            sa.String(),
            nullable=False,
            comment="The name of the related model",
        ),
        sa.Column(
            "observer_id",
            sa.UUID(),
            nullable=False,
            comment="ID of the Observer who created the Observation",
        ),
        sa.Column(
            "created",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
            comment="The time the observation was created",
        ),
        sa.Column(
            "kind", sa.String(), nullable=False, comment="The kind of observation"
        ),
        sa.Column(
            "summary",
            sa.String(),
            nullable=False,
            comment="A short summary of the observation",
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="The observation payload we received",
        ),
        sa.Column(
            "additional",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
            comment="Additional data for the observation",
        ),
        sa.Column(
            "actions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
            comment="Actions taken based on the observation",
        ),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["observer_id"],
            ["observers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["related_id"],
            ["organization_applications.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_organizationapplication_observations_related_id"),
        "organizationapplication_observations",
        ["related_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_organizationapplication_observations_related_id"),
        table_name="organizationapplication_observations",
    )
    op.drop_table("organizationapplication_observations")
