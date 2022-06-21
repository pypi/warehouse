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

import datetime
import enum

from citext import CIText
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    orm,
    select,
    sql,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm.exc import NoResultFound

from warehouse import db
from warehouse.events.models import HasEvents
from warehouse.sitemap.models import SitemapMixin
from warehouse.utils.attrs import make_repr
from warehouse.utils.db.types import TZDateTime


class UserFactory:
    def __init__(self, request):
        self.request = request

    def __getitem__(self, username):
        try:
            return self.request.db.query(User).filter(User.username == username).one()
        except NoResultFound:
            raise KeyError from None


class DisableReason(enum.Enum):

    CompromisedPassword = "password compromised"
    AccountFrozen = "account frozen"


class User(SitemapMixin, HasEvents, db.Model):

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("length(username) <= 50", name="users_valid_username_length"),
        CheckConstraint(
            "username ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'",
            name="users_valid_username",
        ),
    )

    __repr__ = make_repr("username")

    username = Column(CIText, nullable=False, unique=True)
    name = Column(String(length=100), nullable=False)
    password = Column(String(length=128), nullable=False)
    password_date = Column(TZDateTime, nullable=True, server_default=sql.func.now())
    is_active = Column(Boolean, nullable=False, server_default=sql.false())
    is_frozen = Column(Boolean, nullable=False, server_default=sql.false())
    is_superuser = Column(Boolean, nullable=False, server_default=sql.false())
    is_moderator = Column(Boolean, nullable=False, server_default=sql.false())
    is_psf_staff = Column(Boolean, nullable=False, server_default=sql.false())
    prohibit_password_reset = Column(
        Boolean, nullable=False, server_default=sql.false()
    )
    date_joined = Column(DateTime, server_default=sql.func.now())
    last_login = Column(TZDateTime, nullable=False, server_default=sql.func.now())
    disabled_for = Column(
        Enum(DisableReason, values_callable=lambda x: [e.value for e in x]),
        nullable=True,
    )

    totp_secret = Column(LargeBinary(length=20), nullable=True)
    last_totp_value = Column(String, nullable=True)

    webauthn = orm.relationship(
        "WebAuthn", backref="user", cascade="all, delete-orphan", lazy=True
    )
    recovery_codes = orm.relationship(
        "RecoveryCode", backref="user", cascade="all, delete-orphan", lazy=True
    )

    emails = orm.relationship(
        "Email", backref="user", cascade="all, delete-orphan", lazy=False
    )

    macaroons = orm.relationship(
        "Macaroon", backref="user", cascade="all, delete-orphan", lazy=True
    )

    @property
    def primary_email(self):
        primaries = [x for x in self.emails if x.primary]
        if primaries:
            return primaries[0]

    @property
    def public_email(self):
        publics = [x for x in self.emails if x.public]
        if publics:
            return publics[0]

    @hybrid_property
    def email(self):
        primary_email = self.primary_email
        return primary_email.email if primary_email else None

    @email.expression  # type: ignore
    def email(self):
        return (
            select([Email.email])
            .where((Email.user_id == self.id) & (Email.primary.is_(True)))
            .scalar_subquery()
        )

    @property
    def has_two_factor(self):
        return self.totp_secret is not None or len(self.webauthn) > 0

    @property
    def has_recovery_codes(self):
        return any(not code.burned for code in self.recovery_codes)

    @property
    def has_burned_recovery_codes(self):
        return any(code.burned for code in self.recovery_codes)

    @property
    def has_primary_verified_email(self):
        return self.primary_email is not None and self.primary_email.verified

    @property
    def recent_events(self):
        session = orm.object_session(self)
        last_ninety = datetime.datetime.now() - datetime.timedelta(days=90)
        return (
            session.query(User.Event)
            .filter(
                (User.Event.source_id == self.id) & (User.Event.time >= last_ninety)
            )
            .order_by(User.Event.time.desc())
        )

    @property
    def can_reset_password(self):
        return not any(
            [
                self.is_superuser,
                self.is_moderator,
                self.is_psf_staff,
                self.prohibit_password_reset,
            ]
        )


class WebAuthn(db.Model):
    __tablename__ = "user_security_keys"
    __table_args__ = (
        UniqueConstraint("label", "user_id", name="_user_security_keys_label_uc"),
    )

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
        index=True,
    )
    label = Column(String, nullable=False)
    credential_id = Column(String, unique=True, nullable=False)
    public_key = Column(String, unique=True, nullable=True)
    sign_count = Column(Integer, default=0)


class RecoveryCode(db.Model):
    __tablename__ = "user_recovery_codes"

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
        index=True,
    )
    code = Column(String(length=128), nullable=False)
    generated = Column(DateTime, nullable=False, server_default=sql.func.now())
    burned = Column(DateTime, nullable=True)


class UnverifyReasons(enum.Enum):

    SpamComplaint = "spam complaint"
    HardBounce = "hard bounce"
    SoftBounce = "soft bounce"


class Email(db.ModelBase):

    __tablename__ = "user_emails"
    __table_args__ = (
        UniqueConstraint("email", name="user_emails_email_key"),
        Index("user_emails_user_id", "user_id"),
    )

    id = Column(Integer, primary_key=True, nullable=False)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    email = Column(String(length=254), nullable=False)
    primary = Column(Boolean, nullable=False)
    verified = Column(Boolean, nullable=False)
    public = Column(Boolean, nullable=False, server_default=sql.false())

    # Deliverability information
    unverify_reason = Column(
        Enum(UnverifyReasons, values_callable=lambda x: [e.value for e in x]),
        nullable=True,
    )
    transient_bounces = Column(Integer, nullable=False, server_default=sql.text("0"))


class ProhibitedUserName(db.Model):

    __tablename__ = "prohibited_user_names"
    __table_args__ = (
        CheckConstraint(
            "length(name) <= 50", name="prohibited_users_valid_username_length"
        ),
        CheckConstraint(
            "name ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'",
            name="prohibited_users_valid_username",
        ),
    )

    __repr__ = make_repr("name")

    created = Column(
        DateTime(timezone=False), nullable=False, server_default=sql.func.now()
    )
    name = Column(Text, unique=True, nullable=False)
    _prohibited_by = Column(
        "prohibited_by", UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    prohibited_by = orm.relationship(User)
    comment = Column(Text, nullable=False, server_default="")


class TitanPromoCode(db.Model):
    __tablename__ = "user_titan_codes"

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", deferrable=True, initially="DEFERRED"),
        nullable=True,
        index=True,
        unique=True,
    )
    code = Column(String, nullable=False, unique=True)
    created = Column(DateTime, nullable=False, server_default=sql.func.now())
    distributed = Column(DateTime, nullable=True)
