# SPDX-License-Identifier: Apache-2.0
"""
Add project_create_limit_string overrides to users and organizations

Lets admins raise/lower the project-creation rate limit on a per-user
or per-org basis. NULL means "use the configured default for that
bucket". The string is parsed by the limits library at limiter
construction time; validation happens in the admin form, not the DB.

Revision ID: 54e478f6a022
Revises: a3b1c4d5e6f7
Create Date: 2026-05-08 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "54e478f6a022"
down_revision = "a3b1c4d5e6f7"


def upgrade():
    op.add_column(
        "users",
        sa.Column("project_create_limit_string", sa.String(), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "project_create_limit_string",
            sa.String(),
            nullable=True,
            comment=(
                "Override for the project-creation rate limit applied when "
                "creating org-attached projects (e.g. '100 per hour'). NULL "
                "falls back to the global project.create.org default."
            ),
        ),
    )


def downgrade():
    op.drop_column("organizations", "project_create_limit_string")
    op.drop_column("users", "project_create_limit_string")
