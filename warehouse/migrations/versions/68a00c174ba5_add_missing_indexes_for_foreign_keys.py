# SPDX-License-Identifier: Apache-2.0
"""
add missing indexes for foreign keys

Revision ID: 68a00c174ba5
Revises: 42e76a605cac
Create Date: 2018-08-13 16:49:12.920887
"""

from alembic import op

revision = "68a00c174ba5"
down_revision = "42e76a605cac"


def upgrade():
    op.create_index(
        op.f("ix_blacklist_blacklisted_by"),
        "blacklist",
        ["blacklisted_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ses_events_email_id"), "ses_events", ["email_id"], unique=False
    )
    # CREATE INDEX CONCURRENTLY cannot happen inside a transaction. We'll run this
    # outside of the transaction for the migration.
    op.get_bind().commit()
    with op.get_context().autocommit_block():
        op.create_index(
            "journals_submitted_by_idx",
            "journals",
            ["submitted_by"],
            unique=False,
            postgresql_concurrently=True,
        )


def downgrade():
    op.drop_index("journals_submitted_by_idx", table_name="journals")
    op.drop_index(op.f("ix_ses_events_email_id"), table_name="ses_events")
    op.drop_index(op.f("ix_blacklist_blacklisted_by"), table_name="blacklist")
