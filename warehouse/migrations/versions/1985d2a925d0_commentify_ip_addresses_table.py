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
Commentify IP Addresses table

Revision ID: 1985d2a925d0
Revises: 72bba6f541dc
Create Date: 2023-05-11 18:11:08.821920
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "1985d2a925d0"
down_revision = "72bba6f541dc"


def upgrade():
    op.alter_column(
        "ip_addresses",
        "ip_address",
        existing_type=postgresql.INET(),
        comment="Structured IP Address value",
        existing_nullable=False,
    )
    op.alter_column(
        "ip_addresses",
        "hashed_ip_address",
        existing_type=sa.TEXT(),
        comment="Hash that represents an IP Address",
        existing_nullable=True,
    )
    op.alter_column(
        "ip_addresses",
        "geoip_info",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        comment="JSON containing GeoIP data associated with an IP Address",
        existing_nullable=True,
    )
    op.alter_column(
        "ip_addresses",
        "is_banned",
        existing_type=sa.BOOLEAN(),
        comment="If True, this IP Address will be marked as banned",
        existing_nullable=False,
        existing_server_default=sa.text("false"),
    )
    op.alter_column(
        "ip_addresses",
        "ban_reason",
        existing_type=postgresql.ENUM("authentication-attempts", name="banreason"),
        comment="Reason for banning, must be contained in the BanReason enumeration",
        existing_nullable=True,
    )
    op.alter_column(
        "ip_addresses",
        "ban_date",
        existing_type=postgresql.TIMESTAMP(),
        comment="Date that IP Address was last marked as banned",
        existing_nullable=True,
    )
    op.create_table_comment(
        "ip_addresses",
        "Tracks IP Addresses that have modified PyPI state",
        existing_comment=None,
        schema=None,
    )


def downgrade():
    op.drop_table_comment(
        "ip_addresses",
        existing_comment="Tracks IP Addresses that have modified PyPI state",
        schema=None,
    )
    op.alter_column(
        "ip_addresses",
        "ban_date",
        existing_type=postgresql.TIMESTAMP(),
        comment=None,
        existing_comment="Date that IP Address was last marked as banned",
        existing_nullable=True,
    )
    op.alter_column(
        "ip_addresses",
        "ban_reason",
        existing_type=postgresql.ENUM("authentication-attempts", name="banreason"),
        comment=None,
        existing_comment=(
            "Reason for banning, must be contained in the BanReason enumeration"
        ),
        existing_nullable=True,
    )
    op.alter_column(
        "ip_addresses",
        "is_banned",
        existing_type=sa.BOOLEAN(),
        comment=None,
        existing_comment="If True, this IP Address will be marked as banned",
        existing_nullable=False,
        existing_server_default=sa.text("false"),
    )
    op.alter_column(
        "ip_addresses",
        "geoip_info",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        comment=None,
        existing_comment="JSON containing GeoIP data associated with an IP Address",
        existing_nullable=True,
    )
    op.alter_column(
        "ip_addresses",
        "hashed_ip_address",
        existing_type=sa.TEXT(),
        comment=None,
        existing_comment="Hash that represents an IP Address",
        existing_nullable=True,
    )
    op.alter_column(
        "ip_addresses",
        "ip_address",
        existing_type=postgresql.INET(),
        comment=None,
        existing_comment="Structured IP Address value",
        existing_nullable=False,
    )
