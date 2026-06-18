# SPDX-License-Identifier: Apache-2.0
"""
Drop alternate repositories.

Revision ID: a8038ce10051
Revises: 6b38ccac39af
Create Date: 2026-06-18 15:00:16.285161
"""

import sqlalchemy as sa

from alembic import op

revision = "a8038ce10051"
down_revision = "6b38ccac39af"


def upgrade():
    op.drop_table("alternate_repositories")


def downgrade():
    op.create_table(
        "alternate_repositories",
        sa.Column("project_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("name", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column("url", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column("description", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.CheckConstraint(
            "url::text ~* '^https?://.+'::text",
            name=op.f("alternate_repository_valid_url"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("alternate_repositories_project_id_fkey"),
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("alternate_repositories_pkey")),
        sa.UniqueConstraint(
            "project_id",
            "name",
            name=op.f("alternate_repositories_project_id_name_key"),
            postgresql_include=[],
            postgresql_nulls_not_distinct=False,
        ),
        sa.UniqueConstraint(
            "project_id",
            "url",
            name=op.f("alternate_repositories_project_id_url_key"),
            postgresql_include=[],
            postgresql_nulls_not_distinct=False,
        ),
    )
