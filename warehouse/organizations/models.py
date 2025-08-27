# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import datetime
import enum
import typing

from uuid import UUID

from pyramid.authorization import Allow
from pyramid.httpexceptions import HTTPPermanentRedirect
from sqlalchemy import (
    CheckConstraint,
    Date,
    Enum,
    FetchedValue,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    func,
    orm,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import (
    Mapped,
    column_property,
    declared_attr,
    mapped_column,
    relationship,
)

from warehouse import db
from warehouse.accounts.models import TermsOfServiceEngagement, User
from warehouse.authnz import Permissions
from warehouse.events.models import HasEvents
from warehouse.observations.models import HasObservations, ObservationKind
from warehouse.utils.attrs import make_repr
from warehouse.utils.db import orm_session_from_obj
from warehouse.utils.db.types import TZDateTime, bool_false, datetime_now

if typing.TYPE_CHECKING:
    from pyramid.request import Request

    from warehouse.packaging.models import Project
    from warehouse.subscriptions.models import StripeCustomer, StripeSubscription


class OrganizationRoleType(str, enum.Enum):
    Owner = "Owner"
    BillingManager = "Billing Manager"
    Manager = "Manager"
    Member = "Member"


class OrganizationRole(db.Model):
    __tablename__ = "organization_roles"
    __table_args__ = (
        Index("organization_roles_user_id_idx", "user_id"),
        Index("organization_roles_organization_id_idx", "organization_id"),
        UniqueConstraint(
            "user_id",
            "organization_id",
            name="_organization_roles_user_organization_uc",
        ),
    )

    __repr__ = make_repr("role_name")

    role_name: Mapped[OrganizationRoleType] = mapped_column(
        Enum(OrganizationRoleType, values_callable=lambda x: [e.value for e in x]),
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"),
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", onupdate="CASCADE", ondelete="CASCADE"),
    )

    user: Mapped[User] = relationship(back_populates="organization_roles", lazy=False)
    organization: Mapped[Organization] = relationship(
        back_populates="roles", lazy=False
    )


class OrganizationProject(db.Model):
    __tablename__ = "organization_projects"
    __table_args__ = (
        Index("organization_projects_organization_id_idx", "organization_id"),
        Index("organization_projects_project_id_idx", "project_id"),
        UniqueConstraint(
            "organization_id",
            "project_id",
            name="_organization_projects_organization_project_uc",
        ),
    )

    __repr__ = make_repr("project_id", "organization_id")

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", onupdate="CASCADE", ondelete="CASCADE"),
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", onupdate="CASCADE", ondelete="CASCADE"),
    )

    organization: Mapped[Organization] = relationship(lazy=False)
    project: Mapped[Project] = relationship(lazy=False)


class OrganizationStripeSubscription(db.Model):
    __tablename__ = "organization_stripe_subscriptions"
    __table_args__ = (
        Index(
            "organization_stripe_subscriptions_organization_id_idx", "organization_id"
        ),
        Index(
            "organization_stripe_subscriptions_subscription_id_idx", "subscription_id"
        ),
        UniqueConstraint(
            "organization_id",
            "subscription_id",
            name="_organization_stripe_subscriptions_organization_subscription_uc",
        ),
    )

    __repr__ = make_repr("organization_id", "subscription_id")

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", onupdate="CASCADE", ondelete="CASCADE"),
    )
    subscription_id: Mapped[UUID] = mapped_column(
        ForeignKey("stripe_subscriptions.id", onupdate="CASCADE", ondelete="CASCADE"),
    )

    organization: Mapped[Organization] = relationship(lazy=False)
    subscription: Mapped[StripeSubscription] = relationship(lazy=False)


class OrganizationTermsOfServiceEngagement(db.Model):
    __tablename__ = "organization_terms_of_service_engagements"
    __table_args__ = (
        Index(
            "organization_terms_of_service_engagements_org_id_revision_idx",
            "organization_id",
            "revision",
        ),
    )

    __repr__ = make_repr("organization_id")

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", onupdate="CASCADE", ondelete="CASCADE"),
    )
    revision: Mapped[str]
    created: Mapped[datetime.datetime] = mapped_column(TZDateTime)
    engagement: Mapped[TermsOfServiceEngagement]

    organization: Mapped[Organization] = relationship(
        lazy=False, back_populates="terms_of_service_engagements"
    )


class OrganizationStripeCustomer(db.Model):
    __tablename__ = "organization_stripe_customers"
    __table_args__ = (
        Index("organization_stripe_customers_organization_id_idx", "organization_id"),
        Index(
            "organization_stripe_customers_stripe_customer_id_idx", "stripe_customer_id"
        ),
        UniqueConstraint(
            "organization_id",
            "stripe_customer_id",
            name="_organization_stripe_customers_organization_customer_uc",
        ),
    )

    __repr__ = make_repr("organization_id", "stripe_customer_id")

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", onupdate="CASCADE", ondelete="CASCADE"),
    )
    stripe_customer_id: Mapped[UUID] = mapped_column(
        ForeignKey("stripe_customers.id", onupdate="CASCADE", ondelete="CASCADE"),
    )

    organization: Mapped[Organization] = relationship(lazy=False)
    customer: Mapped[StripeCustomer] = relationship(lazy=False)


class OrganizationType(str, enum.Enum):
    Community = "Community"
    Company = "Company"


class OrganizationFactory:
    def __init__(self, request):
        self.request = request

    def __getitem__(self, organization):
        # Try returning organization with matching name.
        try:
            return (
                self.request.db.query(Organization)
                .filter(
                    Organization.normalized_name
                    == func.normalize_pep426_name(organization)
                )
                .one()
            )
        except NoResultFound:
            pass
        # Try redirecting to a renamed organization.
        try:
            organization = (
                self.request.db.query(Organization)
                .join(
                    OrganizationNameCatalog,
                    OrganizationNameCatalog.organization_id == Organization.id,
                )
                .filter(
                    OrganizationNameCatalog.normalized_name
                    == func.normalize_pep426_name(organization)
                )
                .one()
            )
            raise HTTPPermanentRedirect(
                self.request.matched_route.generate(
                    {
                        **self.request.matchdict,
                        "organization_name": organization.normalized_name,
                    }
                )
            )
        except NoResultFound:
            raise KeyError from None


class OrganizationApplicationFactory:
    def __init__(self, request):
        self.request = request

    def __getitem__(self, organization_application_id):
        # Try returning organization application with matching id.
        try:
            return (
                self.request.db.query(OrganizationApplication)
                .filter(OrganizationApplication.id == organization_application_id)
                .one()
            )
        except NoResultFound:
            raise KeyError from None


class OrganizationMixin:
    @declared_attr
    def __table_args__(cls):  # noqa: N805
        return (
            CheckConstraint(
                "name ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'::text",
                name="%s_valid_name" % cls.__tablename__,
            ),
            CheckConstraint(
                "link_url ~* '^https?://.*'::text",
                name="%s_valid_link_url" % cls.__tablename__,
            ),
        )

    name: Mapped[str] = mapped_column(comment="The account name used in URLS")

    display_name: Mapped[str] = mapped_column(comment="Display name used in UI")
    orgtype: Mapped[enum.Enum] = mapped_column(
        Enum(OrganizationType, values_callable=lambda x: [e.value for e in x]),
        comment="What type of organization such as Community or Company",
    )
    link_url: Mapped[str] = mapped_column(
        comment="External URL associated with the organization"
    )
    description: Mapped[str] = mapped_column(
        comment="Description of the business or project the organization represents",
    )


# TODO: Determine if this should also utilize SitemapMixin
class Organization(OrganizationMixin, HasEvents, db.Model):
    __tablename__ = "organizations"

    __repr__ = make_repr("name")

    normalized_name: Mapped[str] = mapped_column(
        unique=True,
        server_default=FetchedValue(),
        server_onupdate=FetchedValue(),
    )
    is_active: Mapped[bool_false] = mapped_column(
        comment="When True, the organization is active and all features are available.",
    )
    created: Mapped[datetime_now] = mapped_column(
        index=True,
        comment="Datetime the organization was created.",
    )
    application: Mapped[OrganizationApplication] = relationship(
        back_populates="organization"
    )

    users: Mapped[list[User]] = relationship(
        secondary=OrganizationRole.__table__,
        back_populates="organizations",
        viewonly=True,
    )
    roles: Mapped[list[OrganizationRole]] = relationship(back_populates="organization")
    invitations: Mapped[list[OrganizationInvitation]] = relationship(
        back_populates="organization"
    )
    teams: Mapped[list[Team]] = relationship(
        back_populates="organization",
        order_by=lambda: Team.name.asc(),
    )
    projects: Mapped[list[Project]] = relationship(
        secondary=OrganizationProject.__table__,
        back_populates="organization",
        viewonly=True,
    )
    customer: Mapped[StripeCustomer] = relationship(
        secondary=OrganizationStripeCustomer.__table__,
        back_populates="organization",
        uselist=False,
        viewonly=True,
    )
    subscriptions: Mapped[list[StripeSubscription]] = relationship(
        secondary=OrganizationStripeSubscription.__table__,
        back_populates="organization",
        viewonly=True,
    )
    terms_of_service_engagements: Mapped[list[OrganizationTermsOfServiceEngagement]] = (
        relationship(
            back_populates="organization",
            viewonly=True,
        )
    )
    manual_activation: Mapped[OrganizationManualActivation] = relationship(
        back_populates="organization",
        uselist=False,
    )

    @property
    def owners(self):
        """Return all users who are owners of the organization."""
        session = orm_session_from_obj(self)
        owner_roles = (
            session.query(User.id)
            .join(OrganizationRole.user)
            .filter(
                OrganizationRole.role_name == OrganizationRoleType.Owner,
                OrganizationRole.organization == self,
            )
            .subquery()
        )
        return session.query(User).join(owner_roles, User.id == owner_roles.c.id).all()

    def record_event(self, *, tag, request: Request = None, additional=None):
        """Record organization name in events in case organization is ever deleted."""
        super().record_event(
            tag=tag,
            request=request,
            additional={"organization_name": self.name, **additional},
        )

    @property
    def good_standing(self):
        """Legacy property - use is_in_good_standing() for new code.

        Check if organization is in good standing and can perform actions.
        """
        return self.is_in_good_standing()

    def is_in_good_standing(self) -> bool:
        """Check if organization is in good standing and can perform actions.

        This is the canonical method for determining if an organization
        meets all requirements to operate (uploads, invitations, etc.).

        Returns True if:
        1. Organization is active (not deleted/deactivated)
        2. For Company organizations: Has active subscription OR active manual
           activation
        3. For Community organizations: Just needs to be active
        """
        if not self.is_active:
            return False

        # Community organizations only need to be active
        if self.orgtype != OrganizationType.Company:
            return True

        # Company organizations need active subscription OR manual activation
        return self.active_subscription is not None or (
            self.manual_activation is not None and self.manual_activation.is_active
        )

    def has_active_billing(self) -> bool:
        """Check if organization has active billing (subscription or manual activation).

        This is specifically for billing status checks, separate from good
        standing status.
        """
        return self.active_subscription is not None or (
            self.manual_activation is not None and self.manual_activation.is_active
        )

    def can_invite_new_members(self) -> bool:
        """Check if organization can invite new members (seat limit enforcement).

        Returns True if:
        1. Organization is in good standing
        2. No seat limit restrictions OR has available seats
        """
        if not self.is_in_good_standing():
            return False

        # Check seat limit for manually activated organizations
        if (
            self.manual_activation is not None
            and self.manual_activation.is_active
            and not self.manual_activation.has_available_seats
        ):
            return False

        return True

    def get_billing_status_display(self) -> str:
        """Get a human-readable billing status for display in forms.

        Returns the organization name with billing status suffix if not in
        good standing.
        """
        if self.good_standing:
            return self.name
        else:
            return f"{self.name} (Billing inactive)"

    def __acl__(self):
        session = orm_session_from_obj(self)

        acls = [
            (
                Allow,
                "group:admins",
                (
                    Permissions.AdminOrganizationsRead,
                    Permissions.AdminOrganizationsWrite,
                    Permissions.AdminOrganizationsNameWrite,
                ),
            ),
            (Allow, "group:moderators", Permissions.AdminOrganizationsRead),
        ]

        # Get all of the users for this organization.
        query = session.query(OrganizationRole).filter(
            OrganizationRole.organization == self
        )
        query = query.options(orm.lazyload(OrganizationRole.organization))
        query = query.join(User).order_by(User.id.asc())
        for role in sorted(
            query.all(),
            key=lambda x: [e.value for e in OrganizationRoleType].index(x.role_name),
        ):
            # *** NOTE ***:
            # When updating these ACLS, please also update the matrix in
            # `warehouse/templates/manage/organization/roles.html` to ensure that
            # the UI is consistent with the actual ACLs.
            #
            # Allow all people in organization read access.
            # Allow write access depending on role.
            if role.role_name == OrganizationRoleType.Owner:
                # Allowed:
                # - View organization (Permissions.OrganizationsRead)
                # - View team (Permissions.OrganizationTeamsRead)
                # - Invite/remove organization member (Permissions.OrganizationsManage)
                # - Create/delete team and add/remove members (OrganizationTeamsManage)
                # - Manage billing (Permissions.OrganizationsBillingManage)
                # - Add project (Permissions.OrganizationProjectsAdd)
                # - Remove project (Permissions.OrganizationProjectsRemove)
                # Disallowed:
                # - (none)
                acls.append(
                    (
                        Allow,
                        f"user:{role.user.id}",
                        [
                            Permissions.OrganizationsRead,
                            Permissions.OrganizationTeamsRead,
                            Permissions.OrganizationsManage,
                            Permissions.OrganizationTeamsManage,
                            Permissions.OrganizationsBillingManage,
                            Permissions.OrganizationProjectsAdd,
                            Permissions.OrganizationProjectsRemove,
                        ],
                    )
                )
            elif role.role_name == OrganizationRoleType.BillingManager:
                # Allowed:
                # - View organization (Permissions.OrganizationsRead)
                # - View team (Permissions.OrganizationTeamsRead)
                # - Manage billing (Permissions.OrganizationsBillingManage)
                # Disallowed:
                # - Invite/remove organization member (Permissions.OrganizationsManage)
                # - Create/delete team and add/remove members (OrganizationTeamsManage)
                # - Add project (Permissions.OrganizationProjectsAdd)
                # - Remove project (Permissions.OrganizationProjectsRemove)
                acls.append(
                    (
                        Allow,
                        f"user:{role.user.id}",
                        [
                            Permissions.OrganizationsRead,
                            Permissions.OrganizationTeamsRead,
                            Permissions.OrganizationsBillingManage,
                        ],
                    )
                )
            elif role.role_name == OrganizationRoleType.Manager:
                # Allowed:
                # - View organization (Permissions.OrganizationsRead)
                # - View team (Permissions.OrganizationTeamsRead)
                # - Create/delete team and add/remove members (OrganizationTeamsManage)
                # - Add project (Permissions.OrganizationProjectsAdd)
                # Disallowed:
                # - Invite/remove organization member (Permissions.OrganizationsManage)
                # - Manage billing (Permissions.OrganizationsBillingManage)
                # - Remove project (Permissions.OrganizationProjectsRemove)
                acls.append(
                    (
                        Allow,
                        f"user:{role.user.id}",
                        [
                            Permissions.OrganizationsRead,
                            Permissions.OrganizationTeamsRead,
                            Permissions.OrganizationTeamsManage,
                            Permissions.OrganizationProjectsAdd,
                        ],
                    )
                )
            else:
                # No member-specific write access needed for now.

                # Allowed:
                # - View organization (Permissions.OrganizationsRead)
                # - View team (Permissions.OrganizationTeamsRead)
                # Disallowed:
                # - Invite/remove organization member (Permissions.OrganizationsManage)
                # - Create/delete team and add/remove members (OrganizationTeamsManage)
                # - Manage billing (Permissions.OrganizationsBillingManage)
                # - Add project (Permissions.OrganizationProjectsAdd)
                # - Remove project (Permissions.OrganizationProjectsRemove)
                acls.append(
                    (
                        Allow,
                        f"user:{role.user.id}",
                        [
                            Permissions.OrganizationsRead,
                            Permissions.OrganizationTeamsRead,
                        ],
                    )
                )
        return acls

    @property
    def active_subscription(self):
        for subscription in self.subscriptions:
            if not subscription.is_restricted:
                return subscription
        else:
            return None

    @property
    def manageable_subscription(self):
        for subscription in self.subscriptions:
            if subscription.is_manageable:
                return subscription
        else:
            return None

    def customer_name(self, site_name="PyPI"):
        return f"{site_name} Organization - {self.display_name} ({self.name})"


class OrganizationManualActivation(db.Model):
    __tablename__ = "organization_manual_activations"

    __repr__ = make_repr("organization_id", "seat_limit", "expires")

    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
        comment="Foreign key to organization",
    )
    organization: Mapped[Organization] = relationship(
        back_populates="manual_activation"
    )

    seat_limit: Mapped[int] = mapped_column(
        Integer, comment="Maximum number of organization members allowed"
    )
    expires: Mapped[datetime.date] = mapped_column(
        Date, comment="Expiration date for the manual activation"
    )
    created: Mapped[datetime_now] = mapped_column(
        comment="Datetime when manual activation was created"
    )
    created_by_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        comment="Admin user who created the manual activation",
    )
    created_by: Mapped[User] = relationship()

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        server_default=text("gen_random_uuid()"),
    )

    @property
    def is_active(self) -> bool:
        """Check if manual activation is currently active (not expired)."""
        return datetime.date.today() < self.expires

    @property
    def current_member_count(self) -> int:
        """Get the current number of organization members."""
        # Use roles count instead of users relationship for more reliable counting
        return len([role for role in self.organization.roles if role.user_id])

    @property
    def has_available_seats(self) -> bool:
        """Check if there are available seats for new members."""
        return self.current_member_count < self.seat_limit

    @property
    def available_seats(self) -> int:
        """Get the number of available seats for new members."""
        return max(0, self.seat_limit - self.current_member_count)


class OrganizationApplicationStatus(enum.StrEnum):
    Submitted = "submitted"
    Declined = "declined"
    Deferred = "deferred"
    MoreInformationNeeded = "moreinformationneeded"
    Approved = "approved"


class OrganizationMembershipSize(enum.StrEnum):
    none = ""
    solo = "1"
    smol = "2-5"
    small = "6-10"
    mid = "11-25"
    medium = "26-50"
    lorge = "51-100"
    large = "100+"


class OrganizationApplication(OrganizationMixin, HasObservations, db.Model):
    __tablename__ = "organization_applications"
    __repr__ = make_repr("name")

    @declared_attr
    def normalized_name(cls):  # noqa: N805
        return column_property(func.normalize_pep426_name(cls.name))

    submitted_by_id: Mapped[UUID] = mapped_column(
        PG_UUID,
        ForeignKey(
            User.id,
            deferrable=True,
            initially="DEFERRED",
            ondelete="CASCADE",
        ),
        comment="ID of the User which submitted the request",
    )
    submitted: Mapped[datetime_now] = mapped_column(
        index=True,
        comment="Datetime the request was submitted",
    )
    updated: Mapped[datetime.datetime | None] = mapped_column(
        onupdate=func.now(),
        comment="Datetime the request was last updated",
    )
    status: Mapped[enum.Enum] = mapped_column(
        Enum(
            OrganizationApplicationStatus,
            values_callable=lambda x: [e.value for e in x],
        ),
        server_default=OrganizationApplicationStatus.Submitted,
        comment="Status of the request",
    )

    usage: Mapped[str | None] = mapped_column(
        comment="Description of how the applicant plans to use Organizations",
    )
    membership_size: Mapped[enum.Enum | None] = mapped_column(
        Enum(
            OrganizationMembershipSize,
            values_callable=lambda x: [e.value for e in x],
        ),
        comment="Anticipated size of Organization Membership",
    )

    organization_id: Mapped[UUID | None] = mapped_column(
        PG_UUID,
        ForeignKey(
            Organization.id,
            deferrable=True,
            initially="DEFERRED",
            ondelete="CASCADE",
        ),
        comment="If the request was approved, ID of resulting Organization",
    )

    submitted_by: Mapped[User] = relationship(
        back_populates="organization_applications"
    )
    organization: Mapped[Organization] = relationship(
        back_populates="application", viewonly=True
    )

    @property
    def information_requests(self):
        return sorted(
            [
                observation
                for observation in self.observations
                if observation.kind == ObservationKind.InformationRequest.value[0]
            ],
            key=lambda x: x.created,
            reverse=True,
        )

    def __lt__(self, other: OrganizationApplication) -> bool:
        return self.name < other.name

    def __acl__(self):
        acls = [
            (
                Allow,
                f"user:{self.submitted_by.id}",
                (Permissions.OrganizationApplicationsManage,),
            )
        ]
        return acls


class OrganizationNameCatalog(db.Model):
    __tablename__ = "organization_name_catalog"
    __table_args__ = (
        Index("organization_name_catalog_normalized_name_idx", "normalized_name"),
        Index("organization_name_catalog_organization_id_idx", "organization_id"),
        UniqueConstraint(
            "normalized_name",
            "organization_id",
            name="_organization_name_catalog_normalized_name_organization_uc",
        ),
        UniqueConstraint(
            "normalized_name",
            name="_organization_name_catalog_normalized_name_uc",
        ),
    )

    __repr__ = make_repr("normalized_name", "organization_id")

    normalized_name: Mapped[str] = mapped_column(index=True)
    organization_id: Mapped[UUID | None] = mapped_column(PG_UUID, index=True)


class OrganizationInvitationStatus(enum.Enum):
    Pending = "pending"
    Expired = "expired"


class OrganizationInvitation(db.Model):
    __tablename__ = "organization_invitations"
    __table_args__ = (
        Index("organization_invitations_user_id_idx", "user_id"),
        UniqueConstraint(
            "user_id",
            "organization_id",
            name="_organization_invitations_user_organization_uc",
        ),
    )

    __repr__ = make_repr("invite_status", "user", "organization")

    invite_status: Mapped[enum.Enum] = mapped_column(
        Enum(
            OrganizationInvitationStatus, values_callable=lambda x: [e.value for e in x]
        ),
    )
    token: Mapped[str]
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"),
        index=True,
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", onupdate="CASCADE", ondelete="CASCADE"),
        index=True,
    )

    user: Mapped[User] = relationship(
        back_populates="organization_invitations", lazy=False
    )
    organization: Mapped[Organization] = relationship(
        back_populates="invitations", lazy=False
    )


class TeamRoleType(str, enum.Enum):
    Member = "Member"


class TeamRole(db.Model):
    __tablename__ = "team_roles"
    __table_args__ = (
        Index("team_roles_user_id_idx", "user_id"),
        Index("team_roles_team_id_idx", "team_id"),
        UniqueConstraint(
            "user_id",
            "team_id",
            name="_team_roles_user_team_uc",
        ),
    )

    __repr__ = make_repr("role_name", "team", "user")

    role_name: Mapped[enum.Enum] = mapped_column(
        Enum(TeamRoleType, values_callable=lambda x: [e.value for e in x]),
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"),
    )
    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", onupdate="CASCADE", ondelete="CASCADE"),
    )

    user: Mapped[User] = relationship(lazy=False)
    team: Mapped[Team] = relationship(lazy=False)


class TeamProjectRoleType(str, enum.Enum):
    Owner = "Owner"  # Granted "Administer" permissions.
    Maintainer = "Maintainer"  # Granted "Upload" permissions.


class TeamProjectRole(db.Model):
    __tablename__ = "team_project_roles"
    __table_args__ = (
        Index("team_project_roles_project_id_idx", "project_id"),
        Index("team_project_roles_team_id_idx", "team_id"),
        UniqueConstraint(
            "project_id",
            "team_id",
            name="_team_project_roles_project_team_uc",
        ),
    )

    __repr__ = make_repr("role_name", "team", "project")

    role_name: Mapped[enum.Enum] = mapped_column(
        Enum(TeamProjectRoleType, values_callable=lambda x: [e.value for e in x]),
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", onupdate="CASCADE", ondelete="CASCADE"),
    )
    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", onupdate="CASCADE", ondelete="CASCADE"),
    )

    project: Mapped[Project] = relationship(
        lazy=False, back_populates="team_project_roles"
    )
    team: Mapped[Team] = relationship(lazy=False)


class TeamFactory:
    def __init__(self, request, organization=None):
        self.request = request
        self.organization = organization

    def __getitem__(self, name):
        if self.organization is None:
            organization = OrganizationFactory(self.request)[name]
            return TeamFactory(self.request, organization)
        try:
            return (
                self.request.db.query(Team)
                .filter(
                    Team.organization == self.organization,
                    Team.normalized_name == func.normalize_pep426_name(name),
                )
                .one()
            )
        except NoResultFound:
            raise KeyError from None


class Team(HasEvents, db.Model):
    __tablename__ = "teams"
    __table_args__ = (
        Index("teams_organization_id_idx", "organization_id"),
        CheckConstraint(
            r"name ~* '^([^\s/._-]|[^\s/._-].*[^\s/._-])$'::text",
            name="teams_valid_name",
        ),
    )

    __repr__ = make_repr("name", "organization")

    name: Mapped[str] = mapped_column()
    normalized_name: Mapped[str] = column_property(func.normalize_team_name(name))
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", onupdate="CASCADE", ondelete="CASCADE"),
    )
    created: Mapped[datetime_now] = mapped_column(index=True)

    organization: Mapped[Organization] = relationship(
        lazy=False, back_populates="teams"
    )
    members: Mapped[list[User]] = relationship(
        secondary=TeamRole.__table__, back_populates="teams", viewonly=True
    )
    projects: Mapped[list[Project]] = relationship(
        secondary=TeamProjectRole.__table__, back_populates="team", viewonly=True
    )

    def record_event(self, *, tag, request: Request = None, additional=None):
        """Record org and team name in events in case they are ever deleted."""
        super().record_event(
            tag=tag,
            request=request,
            additional={
                "organization_name": self.organization.name,
                "team_name": self.name,
                **additional,
            },
        )

    def __acl__(self):
        return self.organization.__acl__()
