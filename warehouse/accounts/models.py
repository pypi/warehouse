# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import datetime
import enum

from typing import TYPE_CHECKING
from uuid import UUID

from pyramid.authorization import Allow, Authenticated
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
    orm,
    select,
    sql,
)
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, UUID as PG_UUID
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column

from warehouse import db
from warehouse.authnz import Permissions
from warehouse.events.models import HasEvents
from warehouse.observations.models import HasObservations, HasObservers, ObservationKind
from warehouse.sitemap.models import SitemapMixin
from warehouse.utils.attrs import make_repr
from warehouse.utils.db import orm_session_from_obj
from warehouse.utils.db.types import TZDateTime, bool_false, datetime_now

if TYPE_CHECKING:
    from warehouse.macaroons.models import Macaroon
    from warehouse.oidc.models import PendingOIDCPublisher
    from warehouse.organizations.models import (
        Organization,
        OrganizationApplication,
        OrganizationInvitation,
        OrganizationRole,
        Team,
    )
    from warehouse.packaging.models import Project, RoleInvitation


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
    AdminInitiated = "admin initiated"


class User(SitemapMixin, HasObservers, HasObservations, HasEvents, db.Model):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("length(username) <= 50", name="users_valid_username_length"),
        CheckConstraint(
            "username ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'",
            name="users_valid_username",
        ),
    )

    __repr__ = make_repr("username")

    username: Mapped[CITEXT] = mapped_column(CITEXT, unique=True)
    name: Mapped[str] = mapped_column(String(length=100))
    password: Mapped[str] = mapped_column(String(length=128))
    password_date: Mapped[datetime.datetime | None] = mapped_column(
        TZDateTime, server_default=sql.func.now()
    )
    is_active: Mapped[bool_false]
    is_frozen: Mapped[bool_false]
    is_superuser: Mapped[bool_false]
    is_support: Mapped[bool_false]
    is_moderator: Mapped[bool_false]
    is_psf_staff: Mapped[bool_false]
    is_observer: Mapped[bool_false] = mapped_column(
        comment="Is this user allowed to add Observations?"
    )
    prohibit_password_reset: Mapped[bool_false]
    hide_avatar: Mapped[bool_false]
    date_joined: Mapped[datetime_now | None]
    last_login: Mapped[datetime.datetime | None] = mapped_column(
        TZDateTime, server_default=sql.func.now()
    )
    disabled_for: Mapped[DisableReason | None]

    totp_secret: Mapped[int | None] = mapped_column(LargeBinary(length=20))
    last_totp_value: Mapped[str | None]

    webauthn: Mapped[list[WebAuthn]] = orm.relationship(
        back_populates="user", cascade="all, delete-orphan", lazy=True
    )

    recovery_codes: Mapped[list[RecoveryCode]] = orm.relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="dynamic"
    )

    emails: Mapped[list[Email]] = orm.relationship(
        back_populates="user", cascade="all, delete-orphan", lazy=False
    )

    macaroons: Mapped[list[Macaroon]] = orm.relationship(
        cascade="all, delete-orphan",
        lazy=True,
        order_by="Macaroon.created.desc()",
    )

    role_invitations: Mapped[list[RoleInvitation]] = orm.relationship(
        "RoleInvitation",
        back_populates="user",
    )

    organization_applications: Mapped[list[OrganizationApplication]] = orm.relationship(
        back_populates="submitted_by",
        cascade="all, delete-orphan",
    )

    organizations: Mapped[list[Organization]] = orm.relationship(
        secondary="organization_roles",
        back_populates="users",
        lazy=True,
        order_by="Organization.name",
        viewonly=True,
    )

    pending_oidc_publishers: Mapped[list[PendingOIDCPublisher]] = orm.relationship(
        back_populates="added_by",
        cascade="all, delete-orphan",
        lazy=True,
    )

    projects: Mapped[list[Project]] = orm.relationship(
        secondary="roles",
        back_populates="users",
        lazy=True,
        viewonly=True,
        order_by="Project.normalized_name",
    )

    organization_roles: Mapped[list[OrganizationRole]] = orm.relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy=True,
        viewonly=True,
    )

    organization_invitations: Mapped[list[OrganizationInvitation]] = orm.relationship(
        back_populates="user",
    )

    teams: Mapped[list[Team]] = orm.relationship(
        secondary="team_roles",
        back_populates="members",
        lazy=True,
        viewonly=True,
        order_by="Team.name",
    )

    terms_of_service_engagements: Mapped[list[UserTermsOfServiceEngagement]] = (
        orm.relationship(
            back_populates="user",
            cascade="all, delete-orphan",
            lazy=True,
            viewonly=True,
        )
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
            select(Email.email)
            .where((Email.user_id == self.id) & (Email.primary.is_(True)))
            .scalar_subquery()
        )

    @property
    def has_two_factor(self):
        return self.has_totp or self.has_webauthn

    @property
    def has_totp(self):
        return self.totp_secret is not None

    @property
    def has_webauthn(self):
        return len(self.webauthn) > 0

    @property
    def has_single_2fa(self):
        if self.has_totp:
            return not self.webauthn
        return len(self.webauthn) == 1

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
        session = orm_session_from_obj(self)
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
                self.is_support,
                self.is_moderator,
                self.is_psf_staff,
                self.prohibit_password_reset,
            ]
        )

    @property
    def active_account_recoveries(self):
        return [
            observation
            for observation in self.observations
            if observation.kind == ObservationKind.AccountRecovery.value[0]
            and observation.additional["status"] == "initiated"
        ]

    def __principals__(self) -> list[str]:
        principals = [Authenticated, f"user:{self.id}"]

        if self.is_superuser:
            principals.append("group:admins")
        if self.is_support:
            principals.append("group:support")
        if self.is_moderator or self.is_superuser or self.is_support:
            principals.append("group:moderators")
        if self.is_psf_staff or self.is_superuser:
            principals.append("group:psf_staff")
        if self.is_observer or self.is_superuser:
            principals.append("group:observers")

        return principals

    def __acl__(self):
        # TODO: This ACL is duplicating permissions set in RootFactory.__acl__
        #   If nothing else, setting the ACL on the model is more restrictive
        #   than RootFactory.__acl__, which is why we duplicate
        #   AdminDashboardSidebarRead here, otherwise the sidebar is not displayed.
        return [
            (
                Allow,
                "group:admins",
                (
                    Permissions.AdminUsersRead,
                    Permissions.AdminUsersWrite,
                    Permissions.AdminUsersEmailWrite,
                    Permissions.AdminUsersAccountRecoveryWrite,
                    Permissions.AdminDashboardSidebarRead,
                ),
            ),
            (
                Allow,
                "group:support",
                (
                    Permissions.AdminUsersRead,
                    Permissions.AdminUsersEmailWrite,
                    Permissions.AdminUsersAccountRecoveryWrite,
                    Permissions.AdminDashboardSidebarRead,
                ),
            ),
            (
                Allow,
                "group:moderators",
                (Permissions.AdminUsersRead, Permissions.AdminDashboardSidebarRead),
            ),
        ]

    def __lt__(self, other):
        return self.username < other.username


class TermsOfServiceEngagement(enum.Enum):
    Flashed = "flashed"
    Notified = "notified"
    Viewed = "viewed"
    Agreed = "agreed"


class UserTermsOfServiceEngagement(db.Model):
    __tablename__ = "user_terms_of_service_engagements"
    __table_args__ = (
        Index(
            "user_terms_of_service_engagements_user_id_revision_idx",
            "user_id",
            "revision",
        ),
    )

    __repr__ = make_repr("user_id")

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"),
    )
    revision: Mapped[str]
    created: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    engagement: Mapped[TermsOfServiceEngagement]

    user: Mapped[User] = orm.relationship(
        lazy=True, back_populates="terms_of_service_engagements"
    )


class WebAuthn(db.Model):
    __tablename__ = "user_security_keys"
    __table_args__ = (
        UniqueConstraint("label", "user_id", name="_user_security_keys_label_uc"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
        index=True,
    )
    user: Mapped[User] = orm.relationship(back_populates="webauthn")
    label: Mapped[str]
    credential_id: Mapped[str] = mapped_column(unique=True)
    public_key: Mapped[str | None] = mapped_column(unique=True)
    sign_count: Mapped[int | None] = mapped_column(default=0)


class RecoveryCode(db.Model):
    __tablename__ = "user_recovery_codes"

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
        index=True,
    )
    user: Mapped[User] = orm.relationship(back_populates="recovery_codes")
    code: Mapped[str] = mapped_column(String(length=128))
    generated: Mapped[datetime_now]
    burned: Mapped[datetime.datetime | None]


class UnverifyReasons(enum.Enum):
    SpamComplaint = "spam complaint"
    HardBounce = "hard bounce"
    SoftBounce = "soft bounce"
    DomainInvalid = "domain status invalid"


class Email(db.ModelBase):
    __tablename__ = "user_emails"
    __table_args__ = (
        UniqueConstraint("email", name="user_emails_email_key"),
        Index("user_emails_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", deferrable=True, initially="DEFERRED"),
    )
    user: Mapped[User] = orm.relationship(back_populates="emails")
    email: Mapped[str] = mapped_column(String(length=254))
    primary: Mapped[bool]
    verified: Mapped[bool]
    public: Mapped[bool_false]

    # Deliverability information
    unverify_reason: Mapped[UnverifyReasons | None]
    transient_bounces: Mapped[int] = mapped_column(server_default=sql.text("0"))

    # Domain validation information
    domain_last_checked: Mapped[datetime.datetime | None] = mapped_column(
        comment="Last time domain was checked with the domain validation service.",
        index=True,
    )
    domain_last_status: Mapped[list[str] | None] = mapped_column(
        ARRAY(String),
        comment="Status strings returned by the domain validation service.",
    )

    @property
    def domain(self):
        return self.email.split("@")[-1].lower()


class ProhibitedEmailDomain(db.Model):
    __tablename__ = "prohibited_email_domains"
    __repr__ = make_repr("domain")

    created: Mapped[datetime_now]
    domain: Mapped[str] = mapped_column(unique=True)
    is_mx_record: Mapped[bool_false] = mapped_column(
        comment="Prohibit any domains that have this domain as an MX record?"
    )
    _prohibited_by: Mapped[UUID | None] = mapped_column(
        "prohibited_by",
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        index=True,
    )
    prohibited_by: Mapped[User] = orm.relationship(User)
    comment: Mapped[str] = mapped_column(server_default="")


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

    created: Mapped[datetime_now]
    name: Mapped[str] = mapped_column(unique=True)
    _prohibited_by: Mapped[UUID | None] = mapped_column(
        "prohibited_by",
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        index=True,
    )
    prohibited_by: Mapped[User] = orm.relationship(User)
    comment: Mapped[str] = mapped_column(server_default="")
