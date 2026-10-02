# SPDX-License-Identifier: Apache-2.0
"""
Add a CheckConstraint to Pending Publishers table

Revision ID: a6045de6d1fe
Revises: ee66c00f12e6
Create Date: 2026-02-11 14:24:19.512201
"""

import sqlalchemy as sa

from alembic import op

revision = "a6045de6d1fe"
down_revision = "ee66c00f12e6"


def upgrade():
    op.create_check_constraint(
        "pending_oidc_publishers_project_name_valid_name",
        "pending_oidc_publishers",
        sa.text("project_name ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'::text"),
    )


def downgrade():
    op.drop_constraint(
        "pending_oidc_publishers_project_name_valid_name",
        "pending_oidc_publishers",
        type_="check",
    )
