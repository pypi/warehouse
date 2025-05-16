# SPDX-License-Identifier: Apache-2.0
"""
check_constraint for ban columns

Revision ID: ef0a77c48089
Revises: f7d91bbfd59e
Create Date: 2022-11-10 20:14:30.253975
"""

from alembic import op

revision = "ef0a77c48089"
down_revision = "f7d91bbfd59e"


def upgrade():
    op.create_check_constraint(
        "ip_addresses_ban_constraints",
        table_name="ip_addresses",
        condition=(
            "(is_banned AND ban_reason IS NOT NULL AND ban_date IS NOT NULL)"
            "OR (NOT is_banned AND ban_reason IS NULL AND ban_date IS NULL)"
        ),
    )


def downgrade():
    op.drop_constraint(
        "ip_addresses_ban_constraints",
        table_name="ip_addresses",
    )
