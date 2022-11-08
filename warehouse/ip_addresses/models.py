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

from sqlalchemy import Boolean, Column, DateTime, Enum, Index, String, sql

from warehouse import db


class BanReason(enum.Enum):
    AUTHENTICATION_ATTEMPTS = "authentication-attempts"


class IpAddress(db.Model):

    __tablename__ = "ip_addresses"
    __table_args__ = (Index("bans_idx", "is_banned"),)

    def __repr__(self):
        return self.ip_address

    ip_address = Column(String, nullable=False, unique=True)
    is_banned = Column(Boolean, nullable=False, server_default=sql.false())
    ban_reason = Column(
        Enum(BanReason, values_callable=lambda x: [e.value for e in x]),
        nullable=True,
    )
    ban_date = Column(DateTime, nullable=True)
