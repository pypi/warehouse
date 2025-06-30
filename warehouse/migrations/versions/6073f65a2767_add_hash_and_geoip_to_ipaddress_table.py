# SPDX-License-Identifier: Apache-2.0
"""
add hash and geoip to IpAddress table

Revision ID: 6073f65a2767
Revises: 2b2f58288de1
Create Date: 2023-05-12 00:37:47.521902
"""

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "6073f65a2767"
down_revision = "2b2f58288de1"


def upgrade():
    op.add_column(
        "ip_addresses",
        sa.Column(
            "hashed_ip_address",
            sa.Text(),
            nullable=True,
            comment="Hash that represents an IP Address",
        ),
    )
    op.add_column(
        "ip_addresses",
        sa.Column(
            "geoip_info",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="JSON containing GeoIP data associated with an IP Address",
        ),
    )
    op.alter_column(
        "ip_addresses",
        "ip_address",
        existing_type=postgresql.INET(),
        comment="Structured IP Address value",
        existing_nullable=False,
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
        comment="Reason for banning, must be in the BanReason enumeration",
        existing_nullable=True,
    )
    op.alter_column(
        "ip_addresses",
        "ban_date",
        existing_type=postgresql.TIMESTAMP(),
        comment="Date that IP Address was last marked as banned",
        existing_nullable=True,
    )
    op.create_unique_constraint(None, "ip_addresses", ["hashed_ip_address"])
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
    op.drop_constraint(None, "ip_addresses", type_="unique")
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
        existing_comment="Reason for banning, must be in the BanReason enumeration",
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
        "ip_address",
        existing_type=postgresql.INET(),
        comment=None,
        existing_comment="Structured IP Address value",
        existing_nullable=False,
    )
    op.drop_column("ip_addresses", "geoip_info")
    op.drop_column("ip_addresses", "hashed_ip_address")
