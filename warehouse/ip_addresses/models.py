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
import enum
import ipaddress

from datetime import datetime

import sentry_sdk

from sqlalchemy import CheckConstraint, Enum, Index
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, validates

from warehouse import db
from warehouse.utils.db.types import bool_false


class BanReason(enum.Enum):
    AUTHENTICATION_ATTEMPTS = "authentication-attempts"


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
    ban_reason: Mapped[Enum | None] = mapped_column(
        Enum(BanReason, values_callable=lambda x: [e.value for e in x]),
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
