# SPDX-License-Identifier: Apache-2.0

import enum
import ipaddress
import typing

from datetime import datetime

import sentry_sdk

from sqlalchemy import CheckConstraint, Index, orm
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, validates

from warehouse import db
from warehouse.utils.db.types import bool_false

if typing.TYPE_CHECKING:
    from warehouse.accounts.models import UserUniqueLogin


class BanReason(enum.Enum):
    AUTHENTICATION_ATTEMPTS = "authentication-attempts"
    ADMINISTRATIVE = "administrative"


class IpAddress(db.Model):
    __tablename__ = "ip_addresses"
    __table_args__ = (
        Index("bans_idx", "is_banned"),
        CheckConstraint(
            "(is_banned AND ban_reason IS NOT NULL AND ban_date IS NOT NULL)"
            "OR (NOT is_banned AND ban_reason IS NULL AND ban_date IS NULL)"
        ),
        {"comment": "Tracks IP Addresses that have modified PyPI state"},
    )

    def __repr__(self) -> str:
        return str(self.ip_address)

    def __lt__(self, other) -> bool:
        return self.id < other.id

    unique_logins: Mapped[list["UserUniqueLogin"]] = orm.relationship(
        back_populates="ip_address",
        cascade="all, delete-orphan",
        lazy=True,
        order_by="UserUniqueLogin.created.desc()",
    )

    ip_address: Mapped[ipaddress.IPv4Address | ipaddress.IPv6Address] = mapped_column(
        INET, unique=True, comment="Structured IP Address value"
    )
    hashed_ip_address: Mapped[str | None] = mapped_column(
        unique=True, comment="Hash that represents an IP Address"
    )
    geoip_info: Mapped[dict | None] = mapped_column(
        JSONB,
        comment="JSON containing GeoIP data associated with an IP Address",
    )

    is_banned: Mapped[bool_false] = mapped_column(
        comment="If True, this IP Address will be marked as banned",
    )
    ban_reason: Mapped[BanReason | None] = mapped_column(
        comment="Reason for banning, must be in the BanReason enumeration",
    )
    ban_date: Mapped[datetime | None] = mapped_column(
        comment="Date that IP Address was last marked as banned",
    )

    @validates("ip_address")
    def validate_ip_address(self, key, ip_address):
        # Check to see if the ip_address is valid
        try:
            _ = ipaddress.ip_address(ip_address)
        except ValueError as e:
            sentry_sdk.capture_message(f"Attempted to store invalid ip_address: {e}")
            # If not, transform it into an IP in the range reserved for documentation
            return "192.0.2.69"  # https://datatracker.ietf.org/doc/html/rfc5737
        return ip_address
