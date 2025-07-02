# SPDX-License-Identifier: Apache-2.0
"""
Add UnverifyReason.DomainInvalid

Revision ID: 082def83d89f
Revises: 13c1c0ac92e9
Create Date: 2025-04-30 20:13:58.084316
"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "082def83d89f"
down_revision = "13c1c0ac92e9"


def upgrade():
    op.sync_enum_values(
        enum_schema="public",
        enum_name="unverifyreasons",
        new_values=[
            "spam complaint",
            "hard bounce",
            "soft bounce",
            "domain status invalid",
        ],
        affected_columns=[
            TableReference(
                table_schema="public",
                table_name="user_emails",
                column_name="unverify_reason",
            )
        ],
        enum_values_to_rename=[],
    )


def downgrade():
    op.sync_enum_values(
        enum_schema="public",
        enum_name="unverifyreasons",
        new_values=["spam complaint", "hard bounce", "soft bounce"],
        affected_columns=[
            TableReference(
                table_schema="public",
                table_name="user_emails",
                column_name="unverify_reason",
            )
        ],
        enum_values_to_rename=[],
    )
