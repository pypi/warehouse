# SPDX-License-Identifier: Apache-2.0
"""
Add issuer_url to GitLab OIDC models

Revision ID: 6aacc97aea2e
Revises: a6994b8bed95
Create Date: 2025-10-07 19:11:23.578974
"""

import sqlalchemy as sa

from alembic import op

revision = "6aacc97aea2e"
down_revision = "a6994b8bed95"


def upgrade():
    # Add column as nullable first
    op.add_column(
        "gitlab_oidc_publishers",
        sa.Column(
            "issuer_url", sa.String(), nullable=True, comment="Full URL of the issuer"
        ),
    )
    op.add_column(
        "pending_gitlab_oidc_publishers",
        sa.Column(
            "issuer_url", sa.String(), nullable=True, comment="Full URL of the issuer"
        ),
    )

    # Set default value for existing records
    op.execute(
        """
        UPDATE gitlab_oidc_publishers SET issuer_url = 'https://gitlab.com'
        WHERE issuer_url IS NULL
        """
    )
    op.execute(
        """
        UPDATE pending_gitlab_oidc_publishers SET issuer_url = 'https://gitlab.com'
        WHERE issuer_url IS NULL
        """
    )

    # Add NOT NULL constraint
    op.alter_column("gitlab_oidc_publishers", "issuer_url", nullable=False)
    op.alter_column("pending_gitlab_oidc_publishers", "issuer_url", nullable=False)


def downgrade():
    op.drop_column("pending_gitlab_oidc_publishers", "issuer_url")
    op.drop_column("gitlab_oidc_publishers", "issuer_url")
