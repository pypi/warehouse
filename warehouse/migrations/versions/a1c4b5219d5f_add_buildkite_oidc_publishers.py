# SPDX-License-Identifier: Apache-2.0
"""
Add Buildkite OIDC publishers

Revision ID: a1c4b5219d5f
Revises: a1c4b5219d5e
Create Date: 2026-08-18 00:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "a1c4b5219d5f"
down_revision = "a1c4b5219d5e"


def _publisher_columns():
    return [
        sa.Column("organization_slug", sa.String(), nullable=False),
        sa.Column("pipeline_slug", sa.String(), nullable=False),
        sa.Column("buildkite_organization_id", sa.String(), nullable=False),
        sa.Column("pipeline_id", sa.String(), nullable=False),
        sa.Column("build_branch", sa.String(), nullable=False),
        sa.Column("build_tag", sa.String(), nullable=False),
        sa.Column("step_key", sa.String(), nullable=False),
    ]


def upgrade():
    op.create_table(
        "buildkite_oidc_publishers",
        sa.Column("id", sa.UUID(), nullable=False),
        *_publisher_columns(),
        sa.ForeignKeyConstraint(["id"], ["oidc_publishers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_slug",
            "pipeline_slug",
            "build_branch",
            "build_tag",
            "step_key",
            name="_buildkite_oidc_publisher_uc",
        ),
    )
    op.create_table(
        "pending_buildkite_oidc_publishers",
        sa.Column("id", sa.UUID(), nullable=False),
        *_publisher_columns(),
        sa.ForeignKeyConstraint(["id"], ["pending_oidc_publishers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_slug",
            "pipeline_slug",
            "build_branch",
            "build_tag",
            "step_key",
            name="_pending_buildkite_oidc_publisher_uc",
        ),
    )


def downgrade():
    op.execute("""
        DELETE FROM macaroons
        WHERE oidc_publisher_id IN (SELECT id FROM buildkite_oidc_publishers)
        """)
    op.execute("""
        DELETE FROM oidc_publisher_project_association
        WHERE oidc_publisher_id IN (SELECT id FROM buildkite_oidc_publishers)
        """)
    op.drop_table("pending_buildkite_oidc_publishers")
    op.execute("""
        DELETE FROM pending_oidc_publishers
        WHERE discriminator = 'pending_buildkite_oidc_publishers'
        """)
    op.drop_table("buildkite_oidc_publishers")
    op.execute("""
        DELETE FROM oidc_publishers
        WHERE discriminator = 'buildkite_oidc_publishers'
        """)
