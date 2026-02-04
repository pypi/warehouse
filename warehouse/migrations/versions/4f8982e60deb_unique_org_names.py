# SPDX-License-Identifier: Apache-2.0
"""
unique_org_names

Revision ID: 4f8982e60deb
Revises: 465f004c9562
Create Date: 2025-04-11 14:03:21.787409
"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "4f8982e60deb"
down_revision = "465f004c9562"


def upgrade():
    op.create_unique_constraint(
        "_organization_name_catalog_normalized_name_uc",
        "organization_name_catalog",
        ["normalized_name"],
    )
    op.sync_enum_values(
        enum_schema="public",
        enum_name="organizationmembershipsize",
        new_values=["", "1", "2-5", "6-10", "11-25", "26-50", "51-100", "100+"],
        affected_columns=[
            TableReference(
                table_schema="public",
                table_name="organization_applications",
                column_name="membership_size",
            )
        ],
        enum_values_to_rename=[],
    )


def downgrade():
    op.sync_enum_values(
        enum_schema="public",
        enum_name="organizationmembershipsize",
        new_values=["1", "2-5", "6-10", "11-25", "26-50", "51-100", "100+"],
        affected_columns=[
            TableReference(
                table_schema="public",
                table_name="organization_applications",
                column_name="membership_size",
            )
        ],
        enum_values_to_rename=[],
    )
    op.drop_constraint(
        "_organization_name_catalog_normalized_name_uc",
        "organization_name_catalog",
        type_="unique",
    )
