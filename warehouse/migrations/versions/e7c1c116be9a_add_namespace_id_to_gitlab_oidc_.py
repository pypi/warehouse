# SPDX-License-Identifier: Apache-2.0
"""
Add namespace_id to GitLab OIDC publishers

Revision ID: e7c1c116be9a
Revises: c7e2a9d41f30
Create Date: 2026-10-28 13:29:21.969376
"""

import sqlalchemy as sa

from alembic import op

revision = "e7c1c116be9a"
down_revision = "c7e2a9d41f30"


def upgrade():
    op.add_column(
        "gitlab_oidc_publishers",
        sa.Column(
            "namespace_id",
            sa.String(),
            nullable=True,
            comment="GitLab namespace ID, recorded from the first accepted token",
        ),
    )


def downgrade():
    op.drop_column("gitlab_oidc_publishers", "namespace_id")
