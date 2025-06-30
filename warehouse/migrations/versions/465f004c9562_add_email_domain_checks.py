# SPDX-License-Identifier: Apache-2.0
"""
Add Email domain checks

Revision ID: 465f004c9562
Revises: e61f32ec7f1d
Create Date: 2025-04-03 15:47:32.961359
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "465f004c9562"
down_revision = "e61f32ec7f1d"


def upgrade():
    op.add_column(
        "user_emails",
        sa.Column(
            "domain_last_checked",
            sa.DateTime(),
            nullable=True,
            comment="Last time domain was checked with the domain validation service.",
        ),
    )
    op.add_column(
        "user_emails",
        sa.Column(
            "domain_last_status",
            postgresql.ARRAY(sa.String()),
            nullable=True,
            comment="Status strings returned by the domain validation service.",
        ),
    )


def downgrade():
    op.drop_column("user_emails", "domain_last_status")
    op.drop_column("user_emails", "domain_last_checked")
