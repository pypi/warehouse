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
add Events in OIDCPublisher

Revision ID: e222887d1d8d
Revises: 26455e3712a2
Create Date: 2024-08-20 10:10:00.329064
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e222887d1d8d"
down_revision = "26455e3712a2"


def upgrade():
    op.create_table(
        "oidcpublisher_events",
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("tag", sa.String(), nullable=False),
        sa.Column(
            "time", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("additional", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip_address_id", sa.UUID(), nullable=True),
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["ip_address_id"],
            ["ip_addresses.id"],
            onupdate="CASCADE",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["oidc_publishers.id"],
            ondelete="CASCADE",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_oidcpublisher_events_source_id",
        "oidcpublisher_events",
        ["source_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_oidcpublisher_events_source_id", table_name="oidcpublisher_events"
    )
    op.drop_table("oidcpublisher_events")
