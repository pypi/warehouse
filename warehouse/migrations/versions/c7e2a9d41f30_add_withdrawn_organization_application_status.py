# SPDX-License-Identifier: Apache-2.0
"""
Add withdrawn to OrganizationApplicationStatus enum

Revision ID: c7e2a9d41f30
Revises: b3c1d8e9f4a2
Create Date: 2026-10-26 00:00:00.000000
"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "c7e2a9d41f30"
down_revision = "b3c1d8e9f4a2"


def upgrade():
    op.execute(
        "ALTER TYPE public.organizationapplicationstatus "
        "ADD VALUE IF NOT EXISTS 'withdrawn'"
    )


def downgrade():
    op.alter_column("organization_applications", "status", server_default=None)
    op.sync_enum_values(
        enum_schema="public",
        enum_name="organizationapplicationstatus",
        new_values=[
            "submitted",
            "declined",
            "deferred",
            "moreinformationneeded",
            "approved",
        ],
        affected_columns=[
            TableReference(
                table_schema="public",
                table_name="organization_applications",
                column_name="status",
            )
        ],
        enum_values_to_rename=[],
    )
    op.alter_column("organization_applications", "status", server_default="submitted")
