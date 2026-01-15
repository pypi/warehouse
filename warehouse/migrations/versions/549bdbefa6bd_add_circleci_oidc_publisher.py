# SPDX-License-Identifier: Apache-2.0
"""
Add CircleCI OIDC publisher

Revision ID: 549bdbefa6bd
Revises: a6cae8e65f1a
Create Date: 2026-01-13 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "549bdbefa6bd"
down_revision = "a6cae8e65f1a"


def upgrade():
    op.create_table(
        "circleci_oidc_publishers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("circleci_org_id", sa.String(), nullable=False),
        sa.Column("circleci_project_id", sa.String(), nullable=False),
        sa.Column("pipeline_definition_id", sa.String(), nullable=False),
        sa.Column("context_id", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["id"],
            ["oidc_publishers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "circleci_org_id",
            "circleci_project_id",
            "pipeline_definition_id",
            "context_id",
            name="_circleci_oidc_publisher_uc",
        ),
    )
    op.create_table(
        "pending_circleci_oidc_publishers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("circleci_org_id", sa.String(), nullable=False),
        sa.Column("circleci_project_id", sa.String(), nullable=False),
        sa.Column("pipeline_definition_id", sa.String(), nullable=False),
        sa.Column("context_id", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["id"],
            ["pending_oidc_publishers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "circleci_org_id",
            "circleci_project_id",
            "pipeline_definition_id",
            "context_id",
            name="_pending_circleci_oidc_publisher_uc",
        ),
    )
    op.execute(
        """
        INSERT INTO admin_flags(id, description, enabled, notify)
        VALUES (
            'disallow-circleci-oidc',
            'Disallow the CircleCI OIDC provider',
            TRUE,
            FALSE
        )
        """
    )


def downgrade():
    op.drop_table("pending_circleci_oidc_publishers")
    op.drop_table("circleci_oidc_publishers")
    op.execute("DELETE FROM admin_flags WHERE id = 'disallow-circleci-oidc'")
