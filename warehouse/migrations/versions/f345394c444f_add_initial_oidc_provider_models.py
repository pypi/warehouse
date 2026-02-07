# SPDX-License-Identifier: Apache-2.0
"""
Add initial OIDC provider models

Revision ID: f345394c444f
Revises: fdf9e337538a
Create Date: 2022-02-15 21:11:41.693791
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f345394c444f"
down_revision = "fdf9e337538a"

# Note: It is VERY important to ensure that a migration does not lock for a
#       long period of time and to ensure that each individual migration does
#       not break compatibility with the *previous* version of the code base.
#       This is because the migrations will be ran automatically as part of the
#       deployment process, but while the previous version of the code is still
#       up and running. Thus backwards incompatible changes must be broken up
#       over multiple migrations inside of multiple pull requests in order to
#       phase them in over multiple deploys.


def upgrade():
    op.create_table(
        "oidc_providers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("discriminator", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "github_oidc_providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repository_name", sa.String(), nullable=True),
        sa.Column("owner", sa.String(), nullable=True),
        sa.Column("owner_id", sa.String(), nullable=True),
        sa.Column("workflow_filename", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["id"],
            ["oidc_providers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "repository_name",
            "owner",
            "workflow_filename",
            name="_github_oidc_provider_uc",
        ),
    )
    op.create_table(
        "oidc_provider_project_association",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("oidc_provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["oidc_provider_id"],
            ["oidc_providers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
        ),
        sa.PrimaryKeyConstraint("id", "oidc_provider_id", "project_id"),
    )
    op.execute("""
        INSERT INTO admin_flags(id, description, enabled, notify)
        VALUES (
            'disallow-oidc',
            'Disallow ALL OpenID Connect behavior, including authentication',
            FALSE,
            FALSE
        )
    """)


def downgrade():
    op.drop_table("oidc_provider_project_association")
    op.drop_table("github_oidc_providers")
    op.drop_table("oidc_providers")
    op.execute("DELETE FROM admin_flags WHERE id = 'disallow-oidc'")
