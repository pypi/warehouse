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
Update gen_random_uuid func path

Revision ID: adb74475e8a4
Revises: bd71566c2877
Create Date: 2022-11-07 20:25:26.983744
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "adb74475e8a4"
down_revision = "bd71566c2877"


def upgrade():
    op.alter_column(
        "prohibited_project_names",
        "id",
        existing_type=postgresql.UUID(),
        server_default=sa.text("gen_random_uuid()"),
        existing_nullable=False,
    )
    op.alter_column(
        "projects",
        "id",
        existing_type=postgresql.UUID(),
        server_default=sa.text("gen_random_uuid()"),
        existing_nullable=False,
    )
    op.alter_column(
        "release_dependencies",
        "id",
        existing_type=postgresql.UUID(),
        server_default=sa.text("gen_random_uuid()"),
        existing_nullable=False,
    )
    op.alter_column(
        "release_files",
        "id",
        existing_type=postgresql.UUID(),
        server_default=sa.text("gen_random_uuid()"),
        existing_nullable=False,
    )
    op.alter_column(
        "releases",
        "id",
        existing_type=postgresql.UUID(),
        server_default=sa.text("gen_random_uuid()"),
        existing_nullable=False,
    )
    op.alter_column(
        "roles",
        "id",
        existing_type=postgresql.UUID(),
        server_default=sa.text("gen_random_uuid()"),
        existing_nullable=False,
    )
    op.alter_column(
        "row_counts",
        "id",
        existing_type=postgresql.UUID(),
        server_default=sa.text("gen_random_uuid()"),
        existing_nullable=False,
    )
    op.alter_column(
        "ses_emails",
        "id",
        existing_type=postgresql.UUID(),
        server_default=sa.text("gen_random_uuid()"),
        existing_nullable=False,
    )
    op.alter_column(
        "ses_events",
        "id",
        existing_type=postgresql.UUID(),
        server_default=sa.text("gen_random_uuid()"),
        existing_nullable=False,
    )
    op.alter_column(
        "users",
        "id",
        existing_type=postgresql.UUID(),
        server_default=sa.text("gen_random_uuid()"),
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        "users",
        "id",
        existing_type=postgresql.UUID(),
        server_default=sa.text("public.gen_random_uuid()"),
        existing_nullable=False,
    )
    op.alter_column(
        "ses_events",
        "id",
        existing_type=postgresql.UUID(),
        server_default=sa.text("public.gen_random_uuid()"),
        existing_nullable=False,
    )
    op.alter_column(
        "ses_emails",
        "id",
        existing_type=postgresql.UUID(),
        server_default=sa.text("public.gen_random_uuid()"),
        existing_nullable=False,
    )
    op.alter_column(
        "row_counts",
        "id",
        existing_type=postgresql.UUID(),
        server_default=sa.text("public.gen_random_uuid()"),
        existing_nullable=False,
    )
    op.alter_column(
        "roles",
        "id",
        existing_type=postgresql.UUID(),
        server_default=sa.text("public.gen_random_uuid()"),
        existing_nullable=False,
    )
    op.alter_column(
        "releases",
        "id",
        existing_type=postgresql.UUID(),
        server_default=sa.text("public.gen_random_uuid()"),
        existing_nullable=False,
    )
    op.alter_column(
        "release_files",
        "id",
        existing_type=postgresql.UUID(),
        server_default=sa.text("public.gen_random_uuid()"),
        existing_nullable=False,
    )
    op.alter_column(
        "release_dependencies",
        "id",
        existing_type=postgresql.UUID(),
        server_default=sa.text("public.gen_random_uuid()"),
        existing_nullable=False,
    )
    op.alter_column(
        "projects",
        "id",
        existing_type=postgresql.UUID(),
        server_default=sa.text("public.gen_random_uuid()"),
        existing_nullable=False,
    )
    op.alter_column(
        "prohibited_project_names",
        "id",
        existing_type=postgresql.UUID(),
        server_default=sa.text("public.gen_random_uuid()"),
        existing_nullable=False,
    )
