# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Generic Events

Revision ID: 5e02c4f9f95c
Revises: 87509f4ae027
Create Date: 2020-07-26 06:12:58.519387
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "5e02c4f9f95c"
down_revision = "84262e097c26"


def upgrade():
    # Create new tables
    op.create_table(
        "projects_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tag", sa.String(), nullable=False),
        sa.Column(
            "time", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("ip_address", sa.String(), nullable=False),
        sa.Column("additional", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"], ["projects.id"], initially="DEFERRED", deferrable=True
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "users_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tag", sa.String(), nullable=False),
        sa.Column(
            "time", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("ip_address", sa.String(), nullable=False),
        sa.Column("additional", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"], ["users.id"], initially="DEFERRED", deferrable=True
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Data migration
    op.execute(
        "INSERT INTO projects_events "
        "(id, source_id, tag, time, ip_address, additional) "
        "SELECT id, project_id, tag, time, ip_address, additional "
        "FROM project_events"
    )
    op.execute(
        "INSERT INTO users_events "
        "(id, source_id, tag, time, ip_address, additional) "
        "SELECT id, user_id, tag, time, ip_address, additional "
        "FROM user_events"
    )

    # Drop old tables
    op.drop_table("user_events")
    op.drop_table("project_events")


def downgrade():
    # Create new tables
    op.create_table(
        "project_events",
        sa.Column(
            "id",
            postgresql.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column("project_id", postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column("tag", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column(
            "time",
            postgresql.TIMESTAMP(),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column("ip_address", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column(
            "additional",
            postgresql.JSONB(astext_type=sa.Text()),
            autoincrement=False,
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="project_events_project_id_fkey",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("id", name="project_events_pkey"),
    )
    op.create_table(
        "user_events",
        sa.Column(
            "id",
            postgresql.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(), autoincrement=False, nullable=False),
        sa.Column("tag", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column(
            "time",
            postgresql.TIMESTAMP(),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column("ip_address", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column(
            "additional",
            postgresql.JSONB(astext_type=sa.Text()),
            autoincrement=False,
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="user_events_user_id_fkey",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("id", name="user_events_pkey"),
    )

    # Data migration
    op.execute(
        "INSERT INTO project_events "
        "(id, project_id, tag, time, ip_address, additional) "
        "SELECT id, source_id, tag, time, ip_address, additional "
        "FROM projects_events"
    )
    op.execute(
        "INSERT INTO user_events "
        "(id, user_id, tag, time, ip_address, additional) "
        "SELECT id, source_id, tag, time, ip_address, additional "
        "FROM users_events"
    )

    # Drop old tables
    op.drop_table("users_events")
    op.drop_table("projects_events")
