# SPDX-License-Identifier: Apache-2.0
"""
Add ActiveState OIDC publisher

Revision ID: 9a0ed2044b53
Revises: e6a1cca38664
Create Date: 2023-11-30 00:05:52.057223
"""

import sqlalchemy as sa

from alembic import op

revision = "9a0ed2044b53"
down_revision = "e6a1cca38664"


def upgrade():
    op.create_table(
        "activestate_oidc_publishers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization", sa.String(), nullable=False),
        sa.Column("activestate_project_name", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.Column("ingredient", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["id"],
            ["oidc_publishers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization",
            "activestate_project_name",
            "actor_id",
            name="_activestate_oidc_publisher_uc",
        ),
    )
    op.create_table(
        "pending_activestate_oidc_publishers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization", sa.String(), nullable=False),
        sa.Column("activestate_project_name", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.Column("ingredient", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["id"],
            ["pending_oidc_publishers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization",
            "activestate_project_name",
            "actor_id",
            name="_pending_activestate_oidc_publisher_uc",
        ),
    )
    # Disable the ActiveState OIDC provider by default
    op.execute("""
        INSERT INTO admin_flags(id, description, enabled, notify)
        VALUES (
            'disallow-activestate-oidc',
            'Disallow the ActiveState OIDC provider',
            TRUE,
            FALSE
        )
        """)


def downgrade():
    op.drop_table("pending_activestate_oidc_publishers")
    op.drop_table("activestate_oidc_publishers")
    op.execute("DELETE FROM admin_flags WHERE id = 'disallow-activestate-oidc'")
