# SPDX-License-Identifier: Apache-2.0
"""
Add CheckConstraint for link_url

Revision ID: 62601ddf674c
Revises: 1d88dd9242e1
Create Date: 2022-12-16 20:58:47.276985
"""

from alembic import op

revision = "62601ddf674c"
down_revision = "1d88dd9242e1"


def upgrade():
    op.create_check_constraint(
        "organizations_valid_link_url",
        "organizations",
        "link_url ~* '^https?://.*'::text",
    )


def downgrade():
    op.drop_constraint("organizations_valid_link_url", "organizations")
