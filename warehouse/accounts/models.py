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

from citext import CIText
from sqlalchemy import (
    CheckConstraint, Column, Enum, ForeignKey, Index, UniqueConstraint,
    Boolean, DateTime, Integer, String,
)
from sqlalchemy import orm, select, sql
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.ext.hybrid import hybrid_property

from warehouse import db
from warehouse.sitemap.models import SitemapMixin
from warehouse.utils.attrs import make_repr


class UserFactory:

    def __init__(self, request):
        self.request = request

    def __getitem__(self, username):
        try:
            return self.request.db.query(User).filter(
                User.username == username
            ).one()
        except NoResultFound:
            raise KeyError from None


class User(SitemapMixin, db.Model):

    __tablename__ = "accounts_user"
    __table_args__ = (
        CheckConstraint("length(username) <= 50", name="packages_valid_name"),
        CheckConstraint(
            "username ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'",
            name="accounts_user_valid_username",
        ),
    )

    __repr__ = make_repr("username")

    username = Column(CIText, nullable=False, unique=True)
    name = Column(String(length=100), nullable=False)
    password = Column(String(length=128), nullable=False)
    password_date = Column(
        DateTime,
        nullable=True,
        server_default=sql.func.now(),
    )
    is_active = Column(Boolean, nullable=False)
    is_staff = Column(Boolean, nullable=False)
    is_superuser = Column(Boolean, nullable=False)
    date_joined = Column(DateTime, server_default=sql.func.now())
    last_login = Column(
        DateTime,
        nullable=False,
        server_default=sql.func.now(),
    )

    emails = orm.relationship(
        "Email",
        backref="user",
        cascade="all, delete-orphan",
        lazy=False,
    )

    @property
    def primary_email(self):
        primaries = [x for x in self.emails if x.primary]
        if primaries:
            return primaries[0]

    @hybrid_property
    def email(self):
        primary_email = self.primary_email
        return primary_email.email if primary_email else None

    @email.expression
    def email(self):
        return (
            select([Email.email])
            .where((Email.user_id == self.id) & (Email.primary.is_(True)))
            .as_scalar()
        )


class UnverifyReasons(enum.Enum):

    SpamComplaint = "spam complaint"
    HardBounce = "hard bounce"
    SoftBounce = "soft bounce"


class Email(db.ModelBase):

    __tablename__ = "accounts_email"
    __table_args__ = (
        UniqueConstraint("email", name="accounts_email_email_key"),

        Index("accounts_email_email_like", "email"),
        Index("accounts_email_user_id", "user_id"),
    )

    id = Column(Integer, primary_key=True, nullable=False)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts_user.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    email = Column(String(length=254), nullable=False)
    primary = Column(Boolean, nullable=False)
    verified = Column(Boolean, nullable=False)

    # Deliverability information
    unverify_reason = Column(
        Enum(UnverifyReasons, values_callable=lambda x: [e.value for e in x]),
        nullable=True,
    )
    transient_bounces = Column(
        Integer,
        nullable=False,
        server_default=sql.text("0"),
    )
