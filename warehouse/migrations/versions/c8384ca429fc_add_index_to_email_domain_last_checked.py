# SPDX-License-Identifier: Apache-2.0
"""
Add Index to Email.domain_last_checked

Revision ID: c8384ca429fc
Revises: f609b35e981b
Create Date: 2025-04-22 18:36:03.844860
"""

from alembic import op

revision = "c8384ca429fc"
down_revision = "f609b35e981b"


def upgrade():
    op.create_index(
        op.f("ix_user_emails_domain_last_checked"),
        "user_emails",
        ["domain_last_checked"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_user_emails_domain_last_checked"), table_name="user_emails")
