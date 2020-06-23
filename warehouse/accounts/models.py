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
    Binary,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    orm,
    select,
    sql,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm.exc import NoResultFound

from warehouse import db
from warehouse.sitemap.models import SitemapMixin
from warehouse.utils.attrs import make_repr


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


class User(SitemapMixin, db.Model):

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
    password_date = Column(DateTime, nullable=True, server_default=sql.func.now())
    is_active = Column(Boolean, nullable=False, server_default=sql.false())
    is_superuser = Column(Boolean, nullable=False, server_default=sql.false())
    is_moderator = Column(Boolean, nullable=False, server_default=sql.false())
    date_joined = Column(DateTime, server_default=sql.func.now())
    last_login = Column(DateTime, nullable=False, server_default=sql.func.now())
    disabled_for = Column(
        Enum(DisableReason, values_callable=lambda x: [e.value for e in x]),
        nullable=True,
    )

    totp_secret = Column(Binary(length=20), nullable=True)
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

    events = orm.relationship(
        "UserEvent", backref="user", cascade="all, delete-orphan", lazy=True
    )

    def record_event(self, *, tag, ip_address, additional):
        session = orm.object_session(self)
        event = UserEvent(
            user=self, tag=tag, ip_address=ip_address, additional=additional
        )
        session.add(event)
        session.flush()

        return event

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

    @email.expression
    def email(self):
        return (
            select([Email.email])
            .where((Email.user_id == self.id) & (Email.primary.is_(True)))
            .as_scalar()
        )

    @property
    def has_two_factor(self):
        return self.totp_secret is not None or len(self.webauthn) > 0

    @property
    def has_recovery_codes(self):
        return len(self.recovery_codes) > 0

    @property
    def has_primary_verified_email(self):
        return self.primary_email is not None and self.primary_email.verified

    @property
    def recent_events(self):
        session = orm.object_session(self)
        last_ninety = datetime.datetime.now() - datetime.timedelta(days=90)
        return (
            session.query(UserEvent)
            .filter((UserEvent.user_id == self.id) & (UserEvent.time >= last_ninety))
            .order_by(UserEvent.time.desc())
            .all()
        )

    @property
    def recent_emails(self):
        from warehouse.email.ses.models import EmailMessage

        session = orm.object_session(self)
        last_ninety = datetime.datetime.now() - datetime.timedelta(days=90)
        user_emails = [x.email for x in self.emails]
        return (
            session.query(EmailMessage)
            .filter(
                (EmailMessage.to.in_(user_emails))
                & (EmailMessage.created >= last_ninety)
            )
            .order_by(EmailMessage.created.desc())
            .all()
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
    )
    code = Column(String(length=128), nullable=False)
    generated = Column(DateTime, nullable=False, server_default=sql.func.now())


class UserEvent(db.Model):
    __tablename__ = "user_events"

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    tag = Column(String, nullable=False)
    time = Column(DateTime, nullable=False, server_default=sql.func.now())
    ip_address = Column(String, nullable=False)
    additional = Column(JSONB, nullable=True)


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
