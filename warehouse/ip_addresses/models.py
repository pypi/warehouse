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

import sentry_sdk

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, Index, Text, sql
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import mapped_column, validates

from warehouse import db


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

    def __lt__(self, other):
        return self.id < other.id

    ip_address = mapped_column(
        INET, nullable=False, unique=True, comment="Structured IP Address value"
    )
    hashed_ip_address = mapped_column(
        Text, nullable=True, unique=True, comment="Hash that represents an IP Address"
    )
    geoip_info = mapped_column(
        JSONB,
        nullable=True,
        comment="JSON containing GeoIP data associated with an IP Address",
    )

    is_banned = mapped_column(
        Boolean,
        nullable=False,
        server_default=sql.false(),
        comment="If True, this IP Address will be marked as banned",
    )
    ban_reason = mapped_column(  # type: ignore[var-annotated]
        Enum(BanReason, values_callable=lambda x: [e.value for e in x]),
        nullable=True,
        comment="Reason for banning, must be in the BanReason enumeration",
    )
    ban_date = mapped_column(
        DateTime,
        nullable=True,
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
