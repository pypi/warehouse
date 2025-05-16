# SPDX-License-Identifier: Apache-2.0
"""
Event.source_id cascades on delete

Revision ID: 203f1f8dcf92
Revises: d64193adcd10
Create Date: 2023-03-20 21:31:48.032660
"""


import sqlalchemy as sa

from alembic import op

revision = "203f1f8dcf92"
down_revision = "d64193adcd10"


def upgrade():
    # We've seen this migration fail due to statement timeouts in production.
    conn = op.get_bind()
    conn.execute(sa.text("SET statement_timeout = 60000"))

    op.drop_constraint("file_events_source_id_fkey", "file_events", type_="foreignkey")
    op.create_foreign_key(
        None,
        "file_events",
        "release_files",
        ["source_id"],
        ["id"],
        ondelete="CASCADE",
        initially="DEFERRED",
        deferrable=True,
    )
    op.drop_constraint(
        "organization_events_source_id_fkey", "organization_events", type_="foreignkey"
    )
    op.create_foreign_key(
        None,
        "organization_events",
        "organizations",
        ["source_id"],
        ["id"],
        ondelete="CASCADE",
        initially="DEFERRED",
        deferrable=True,
    )
    op.drop_constraint(
        "project_events_source_id_fkey", "project_events", type_="foreignkey"
    )
    op.create_foreign_key(
        None,
        "project_events",
        "projects",
        ["source_id"],
        ["id"],
        ondelete="CASCADE",
        initially="DEFERRED",
        deferrable=True,
    )
    op.drop_constraint("team_events_source_id_fkey", "team_events", type_="foreignkey")
    op.create_foreign_key(
        None,
        "team_events",
        "teams",
        ["source_id"],
        ["id"],
        ondelete="CASCADE",
        initially="DEFERRED",
        deferrable=True,
    )
    op.drop_constraint("user_events_user_id_fkey", "user_events", type_="foreignkey")
    op.create_foreign_key(
        None,
        "user_events",
        "users",
        ["source_id"],
        ["id"],
        ondelete="CASCADE",
        initially="DEFERRED",
        deferrable=True,
    )


def downgrade():
    op.drop_constraint(None, "user_events", type_="foreignkey")
    op.create_foreign_key(
        "user_events_user_id_fkey",
        "user_events",
        "users",
        ["source_id"],
        ["id"],
        initially="DEFERRED",
        deferrable=True,
    )
    op.drop_constraint(None, "team_events", type_="foreignkey")
    op.create_foreign_key(
        "team_events_source_id_fkey",
        "team_events",
        "teams",
        ["source_id"],
        ["id"],
        initially="DEFERRED",
        deferrable=True,
    )
    op.drop_constraint(None, "project_events", type_="foreignkey")
    op.create_foreign_key(
        "project_events_source_id_fkey",
        "project_events",
        "projects",
        ["source_id"],
        ["id"],
        initially="DEFERRED",
        deferrable=True,
    )
    op.drop_constraint(None, "organization_events", type_="foreignkey")
    op.create_foreign_key(
        "organization_events_source_id_fkey",
        "organization_events",
        "organizations",
        ["source_id"],
        ["id"],
        initially="DEFERRED",
        deferrable=True,
    )
    op.drop_constraint(None, "file_events", type_="foreignkey")
    op.create_foreign_key(
        "file_events_source_id_fkey",
        "file_events",
        "release_files",
        ["source_id"],
        ["id"],
        initially="DEFERRED",
        deferrable=True,
    )
