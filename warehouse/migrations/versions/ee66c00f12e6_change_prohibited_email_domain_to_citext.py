# SPDX-License-Identifier: Apache-2.0
"""
Change prohibited_email_domains.domain to CITEXT

Revision ID: ee66c00f12e6
Revises: 31ac9b5e1e8b
Create Date: 2026-02-03
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects.postgresql import CITEXT

revision = "ee66c00f12e6"
down_revision = "31ac9b5e1e8b"


def upgrade():
    op.alter_column(
        "prohibited_email_domains",
        "domain",
        existing_type=sa.String(),
        type_=CITEXT(),
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        "prohibited_email_domains",
        "domain",
        existing_type=CITEXT(),
        type_=sa.String(),
        existing_nullable=False,
    )
