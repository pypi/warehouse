# SPDX-License-Identifier: Apache-2.0
"""
Cascade project_events deletion

Revision ID: 69b928240b2f
Revises: 99a201142761
Create Date: 2021-02-08 21:45:22.759363
"""

from alembic import op

revision = "69b928240b2f"
down_revision = "99a201142761"


def upgrade():
    op.drop_constraint(
        "project_events_project_id_fkey", "project_events", type_="foreignkey"
    )
    op.create_foreign_key(
        None,
        "project_events",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
        initially="DEFERRED",
        deferrable=True,
    )


def downgrade():
    op.drop_constraint(None, "project_events", type_="foreignkey")
    op.create_foreign_key(
        "project_events_project_id_fkey",
        "project_events",
        "projects",
        ["project_id"],
        ["id"],
        initially="DEFERRED",
        deferrable=True,
    )
