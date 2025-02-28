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
File events

Revision ID: d64193adcd10
Revises: eb736cb3236d
Create Date: 2023-03-15 17:36:12.321663
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d64193adcd10"
down_revision = "eb736cb3236d"


def upgrade():
    op.create_table(
        "file_events",
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
        sa.Column("ip_address_string", sa.String(), nullable=True),
        sa.Column("additional", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip_address_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ip_address_id"],
            ["ip_addresses.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["release_files.id"], initially="DEFERRED", deferrable=True
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_file_events_source_id", "file_events", ["source_id"], unique=False
    )


def downgrade():
    op.drop_index("ix_file_events_source_id", table_name="file_events")
    op.drop_table("file_events")
