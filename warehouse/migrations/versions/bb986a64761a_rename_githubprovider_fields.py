# SPDX-License-Identifier: Apache-2.0
"""
rename GitHubProvider fields

Revision ID: bb986a64761a
Revises: 9f0f99509d92
Create Date: 2022-04-22 22:00:53.832695
"""

from alembic import op

revision = "bb986a64761a"
down_revision = "9f0f99509d92"


def upgrade():
    op.drop_constraint(
        "_github_oidc_provider_uc", "github_oidc_providers", type_="unique"
    )
    op.alter_column(
        "github_oidc_providers", "owner_id", new_column_name="repository_owner_id"
    )
    op.alter_column(
        "github_oidc_providers", "owner", new_column_name="repository_owner"
    )
    op.create_unique_constraint(
        "_github_oidc_provider_uc",
        "github_oidc_providers",
        ["repository_name", "repository_owner", "workflow_filename"],
    )


def downgrade():
    op.drop_constraint(
        "_github_oidc_provider_uc", "github_oidc_providers", type_="unique"
    )
    op.alter_column(
        "github_oidc_providers", "repository_owner_id", new_column_name="owner_id"
    )
    op.alter_column(
        "github_oidc_providers", "repository_owner", new_column_name="owner"
    )
    op.create_unique_constraint(
        "_github_oidc_provider_uc",
        "github_oidc_providers",
        ["repository_name", "owner", "workflow_filename"],
    )
