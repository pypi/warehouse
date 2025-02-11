# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Add tables for storing SES information

Revision ID: 7f0d1b5af8c7
Revises: 6418f7d86a4b
Create Date: 2018-04-02 15:29:59.499569
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "7f0d1b5af8c7"
down_revision = "6418f7d86a4b"


SESEmailStatuses = sa.Enum(
    "Accepted",
    "Delivered",
    "Soft Bounced",
    "Bounced",
    "Complained",
    name="ses_email_statuses",
)


SESEventTypes = sa.Enum("Delivery", "Bounce", "Complaint", name="ses_event_types")

EmailFailureTypes = sa.Enum(
    "spam complaint", "hard bounce", "soft bounce", name="accounts_email_failure_types"
)


def upgrade():
    op.create_table(
        "ses_emails",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "status", SESEmailStatuses, nullable=False, server_default="Accepted"
        ),
        sa.Column("message_id", sa.Text(), nullable=False),
        sa.Column("from", sa.Text(), nullable=False),
        sa.Column("to", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_ses_emails_message_id"), "ses_emails", ["message_id"], unique=True
    )

    op.create_index(op.f("ix_ses_emails_to"), "ses_emails", ["to"], unique=False)

    op.create_table(
        "ses_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("email_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("event_type", SESEventTypes, nullable=False),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["email_id"], ["ses_emails.id"], initially="DEFERRED", deferrable=True
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_ses_events_event_id"), "ses_events", ["event_id"], unique=True
    )

    EmailFailureTypes.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "accounts_email", sa.Column("unverify_reason", EmailFailureTypes, nullable=True)
    )

    op.add_column(
        "accounts_email",
        sa.Column(
            "transient_bounces",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("accounts_email", "transient_bounces")
    op.drop_column("accounts_email", "unverify_reason")
    op.drop_index(op.f("ix_ses_events_event_id"), table_name="ses_events")
    op.drop_table("ses_events")
    op.drop_index(op.f("ix_ses_emails_message_id"), table_name="ses_emails")
    op.drop_index(op.f("ix_ses_emails_to"), table_name="ses_emails")
    op.drop_table("ses_emails")
    SESEventTypes.drop(op.get_bind())
    SESEmailStatuses.drop(op.get_bind())
    EmailFailureTypes.drop(op.get_bind())
