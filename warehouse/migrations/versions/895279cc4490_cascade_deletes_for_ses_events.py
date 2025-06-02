# SPDX-License-Identifier: Apache-2.0
"""
Cascade deletes for SES Events and add an Index on the status.

Revision ID: 895279cc4490
Revises: b00323b3efd8
Create Date: 2018-08-03 21:21:23.695625
"""

from alembic import op

revision = "895279cc4490"
down_revision = "b00323b3efd8"


def upgrade():
    op.create_index(
        op.f("ix_ses_emails_status"), "ses_emails", ["status"], unique=False
    )
    op.drop_constraint("ses_events_email_id_fkey", "ses_events", type_="foreignkey")
    op.create_foreign_key(
        None,
        "ses_events",
        "ses_emails",
        ["email_id"],
        ["id"],
        ondelete="CASCADE",
        initially="DEFERRED",
        deferrable=True,
    )


def downgrade():
    raise RuntimeError("Order No. 227 - Ни шагу назад!")
