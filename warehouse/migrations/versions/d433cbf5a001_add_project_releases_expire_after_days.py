# SPDX-License-Identifier: Apache-2.0
"""
Add Project.releases_expire_after_days

Revision ID: d433cbf5a001
Revises: 28c1e0646708
Create Date: 2026-02-18 18:32:06.895984
"""

import sqlalchemy as sa

from alembic import op

revision = "d433cbf5a001"
down_revision = "28c1e0646708"


def upgrade():
    op.add_column(
        "projects",
        sa.Column(
            "releases_expire_after_days",
            sa.Integer(),
            nullable=True,
            comment="If set, releases for this project will be automatically deleted "
            "after this many days.",
        ),
    )


def downgrade():
    op.drop_column("projects", "releases_expire_after_days")
