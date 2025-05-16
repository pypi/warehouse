# SPDX-License-Identifier: Apache-2.0
"""
Update GH publisher constraints

Revision ID: f7cd7a943caa
Revises: 689dea7d202a
Create Date: 2023-04-12 14:20:36.152729
"""

from alembic import op

revision = "f7cd7a943caa"
down_revision = "689dea7d202a"


def upgrade():
    op.drop_constraint(
        "_github_oidc_publisher_uc", "github_oidc_publishers", type_="unique"
    )
    op.create_unique_constraint(
        "_github_oidc_publisher_uc",
        "github_oidc_publishers",
        ["repository_name", "repository_owner", "workflow_filename", "environment"],
    )
    op.drop_constraint(
        "_pending_github_oidc_publisher_uc",
        "pending_github_oidc_publishers",
        type_="unique",
    )
    op.create_unique_constraint(
        "_pending_github_oidc_publisher_uc",
        "pending_github_oidc_publishers",
        ["repository_name", "repository_owner", "workflow_filename", "environment"],
    )


def downgrade():
    op.drop_constraint(
        "_pending_github_oidc_publisher_uc",
        "pending_github_oidc_publishers",
        type_="unique",
    )
    op.create_unique_constraint(
        "_pending_github_oidc_publisher_uc",
        "pending_github_oidc_publishers",
        ["repository_name", "repository_owner", "workflow_filename"],
    )
    op.drop_constraint(
        "_github_oidc_publisher_uc", "github_oidc_publishers", type_="unique"
    )
    op.create_unique_constraint(
        "_github_oidc_publisher_uc",
        "github_oidc_publishers",
        ["repository_name", "repository_owner", "workflow_filename"],
    )
