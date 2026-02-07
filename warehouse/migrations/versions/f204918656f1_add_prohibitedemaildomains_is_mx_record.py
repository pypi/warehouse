# SPDX-License-Identifier: Apache-2.0
"""
Add ProhibitedEmailDomains.is_mx_record

Revision ID: f204918656f1
Revises: 1b9ae6ec6ec0
Create Date: 2024-09-09 20:04:30.136554
"""

import sqlalchemy as sa

from alembic import op

revision = "f204918656f1"
down_revision = "1b9ae6ec6ec0"


def upgrade():
    op.add_column(
        "prohibited_email_domains",
        sa.Column(
            "is_mx_record",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=True,
            comment="Prohibit any domains that have this domain as an MX record?",
        ),
    )
    op.execute("""
        UPDATE prohibited_email_domains
        SET is_mx_record = false
        WHERE is_mx_record IS NULL
    """)
    op.alter_column("prohibited_email_domains", "is_mx_record", nullable=False)


def downgrade():
    op.drop_column("prohibited_email_domains", "is_mx_record")
