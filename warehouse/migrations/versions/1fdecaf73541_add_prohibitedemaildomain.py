# SPDX-License-Identifier: Apache-2.0
"""
Add ProhibitedEmailDomain

Revision ID: 1fdecaf73541
Revises: 93a1ca43e356
Create Date: 2024-03-28 02:23:25.712347
"""

import sqlalchemy as sa

from alembic import op

revision = "1fdecaf73541"
down_revision = "93a1ca43e356"


def upgrade():
    op.create_table(
        "prohibited_email_domains",
        sa.Column(
            "created", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("prohibited_by", sa.UUID(), nullable=True),
        sa.Column("comment", sa.String(), server_default="", nullable=False),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["prohibited_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("domain"),
    )
    op.create_index(
        op.f("ix_prohibited_email_domains_prohibited_by"),
        "prohibited_email_domains",
        ["prohibited_by"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_prohibited_email_domains_prohibited_by"),
        table_name="prohibited_email_domains",
    )
    op.drop_table("prohibited_email_domains")
