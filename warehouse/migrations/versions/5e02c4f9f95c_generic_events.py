# SPDX-License-Identifier: Apache-2.0
"""
Generic Events

Revision ID: 5e02c4f9f95c
Revises: 87509f4ae027
Create Date: 2020-07-26 06:12:58.519387
"""

from alembic import op

revision = "5e02c4f9f95c"
down_revision = "84262e097c26"


def upgrade():
    op.alter_column("project_events", "project_id", new_column_name="source_id")
    op.execute(
        "ALTER INDEX ix_project_events_project_id RENAME TO ix_project_events_source_id"  # noqa
    )

    op.alter_column("user_events", "user_id", new_column_name="source_id")
    op.execute("ALTER INDEX ix_user_events_user_id RENAME TO ix_user_events_source_id")


def downgrade():
    op.alter_column("project_events", "source_id", new_column_name="project_id")
    op.execute(
        "ALTER INDEX ix_project_events_source_id RENAME TO ix_project_events_project_id"  # noqa
    )

    op.alter_column("user_events", "source_id", new_column_name="user_id")
    op.execute("ALTER INDEX ix_user_events_source_id RENAME TO ix_user_events_user_id")
