# SPDX-License-Identifier: Apache-2.0
"""
Add GitLab OIDC models

Revision ID: 81f9f9a60270
Revises: 4d1b4fcc4076
Create Date: 2024-01-16 17:46:16.443395
"""

import sqlalchemy as sa

from alembic import op

revision = "81f9f9a60270"
down_revision = "4d1b4fcc4076"


def upgrade():
    op.execute("""
        INSERT INTO admin_flags(id, description, enabled, notify)
        VALUES (
            'disallow-gitlab-oidc',
            'Disallow the GitLab OIDC provider',
            TRUE,
            FALSE
        )
        """)
    op.create_table(
        "gitlab_oidc_publishers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("namespace", sa.String(), nullable=False),
        sa.Column("project", sa.String(), nullable=False),
        sa.Column("workflow_filepath", sa.String(), nullable=False),
        sa.Column("environment", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["oidc_publishers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "namespace",
            "project",
            "workflow_filepath",
            "environment",
            name="_gitlab_oidc_publisher_uc",
        ),
    )
    op.create_table(
        "pending_gitlab_oidc_publishers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("namespace", sa.String(), nullable=False),
        sa.Column("project", sa.String(), nullable=False),
        sa.Column("workflow_filepath", sa.String(), nullable=False),
        sa.Column("environment", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["id"],
            ["pending_oidc_publishers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "namespace",
            "project",
            "workflow_filepath",
            "environment",
            name="_pending_gitlab_oidc_publisher_uc",
        ),
    )


def downgrade():
    op.execute("DELETE FROM admin_flags WHERE id = 'disallow-gitlab-oidc'")
    op.drop_table("pending_gitlab_oidc_publishers")
    op.drop_table("gitlab_oidc_publishers")
