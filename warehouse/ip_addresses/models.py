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

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Enum, Index, sql
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import validates

from warehouse import db


class BanReason(enum.Enum):
    AUTHENTICATION_ATTEMPTS = "authentication-attempts"


class IpAddress(db.Model):

    __tablename__ = "ip_addresses"
    __table_args__ = (
        Index("bans_idx", "is_banned"),
        CheckConstraint(
            "NOT is_banned <> NOT (ban_reason IS NULL OR ban_date IS NULL)"
        ),
    )

    def __repr__(self):
        return self.ip_address

    ip_address = Column(INET, nullable=False, unique=True)
    is_banned = Column(Boolean, nullable=False, server_default=sql.false())
    ban_reason = Column(
        Enum(BanReason, values_callable=lambda x: [e.value for e in x]),
        nullable=True,
    )
    ban_date = Column(DateTime, nullable=True)

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
