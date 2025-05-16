# SPDX-License-Identifier: Apache-2.0
"""
Add a column to track if the email was missing

Revision ID: 6714f3f04f0f
Revises: 7f0d1b5af8c7
Create Date: 2018-04-15 06:05:36.949018
"""

import sqlalchemy as sa

from alembic import op

revision = "6714f3f04f0f"
down_revision = "7f0d1b5af8c7"


def upgrade():
    op.add_column(
        "ses_emails",
        sa.Column(
            "missing", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )


def downgrade():
    op.drop_column("ses_emails", "missing")
