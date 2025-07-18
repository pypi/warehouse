# SPDX-License-Identifier: Apache-2.0
"""
Add OIDCPublisherProjectAssociation constraint

Revision ID: 30c837b1425a
Revises: 082def83d89f
Create Date: 2025-07-17 17:53:57.897999
"""

from alembic import op

revision = "30c837b1425a"
down_revision = "082def83d89f"


def upgrade():
    op.create_unique_constraint(
        None, "oidc_publisher_project_association", ["oidc_publisher_id", "project_id"]
    )


def downgrade():
    op.drop_constraint(None, "oidc_publisher_project_association", type_="unique")
