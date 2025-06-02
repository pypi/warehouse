# SPDX-License-Identifier: Apache-2.0
"""
Make GitHubPublisher environment non-nullable

Revision ID: a8ebe73ccaf2
Revises: a2af745511e0
Create Date: 2023-08-16 19:48:03.178852
"""

import sqlalchemy as sa

from alembic import op

revision = "a8ebe73ccaf2"
down_revision = "a2af745511e0"


def upgrade():
    # Data migration
    op.execute(
        "UPDATE github_oidc_publishers SET environment = '' where environment IS NULL"
    )
    op.execute(
        "UPDATE pending_github_oidc_publishers "
        "SET environment = '' where environment IS NULL"
    )

    op.alter_column(
        "github_oidc_publishers",
        "environment",
        existing_type=sa.VARCHAR(),
        nullable=False,
    )
    op.alter_column(
        "pending_github_oidc_publishers",
        "environment",
        existing_type=sa.VARCHAR(),
        nullable=False,
    )


def downgrade():
    op.alter_column(
        "pending_github_oidc_publishers",
        "environment",
        existing_type=sa.VARCHAR(),
        nullable=True,
    )
    op.alter_column(
        "github_oidc_publishers",
        "environment",
        existing_type=sa.VARCHAR(),
        nullable=True,
    )

    # Data migration
    op.execute(
        "UPDATE github_oidc_publishers SET environment = NULL where environment = ''"
    )
    op.execute(
        "UPDATE pending_github_oidc_publishers "
        "SET environment = NULL where environment = ''"
    )
