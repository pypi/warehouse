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
from __future__ import annotations

import enum
import typing

from pyramid.authorization import Allow
from pyramid.httpexceptions import HTTPPermanentRedirect
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
    orm,
    sql,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import declared_attr, mapped_column

from warehouse import db
from warehouse.accounts.models import User
from warehouse.events.models import HasEvents
from warehouse.utils.attrs import make_repr

if typing.TYPE_CHECKING:
    from pyramid.request import Request


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

    role_name = mapped_column(
        Enum(OrganizationRoleType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    user_id = mapped_column(
        ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False
    )
    organization_id = mapped_column(
        ForeignKey("organizations.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )

    user = orm.relationship(User, lazy=False)
    organization = orm.relationship("Organization", lazy=False)


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

    organization_id = mapped_column(
        ForeignKey("organizations.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    project_id = mapped_column(
        ForeignKey("projects.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )

    organization = orm.relationship("Organization", lazy=False)
    project = orm.relationship("Project", lazy=False)


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

    organization_id = mapped_column(
        ForeignKey("organizations.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    subscription_id = mapped_column(
        ForeignKey("stripe_subscriptions.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )

    organization = orm.relationship("Organization", lazy=False)
    subscription = orm.relationship("StripeSubscription", lazy=False)


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

    organization_id = mapped_column(
        ForeignKey("organizations.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    stripe_customer_id = mapped_column(
        ForeignKey("stripe_customers.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )

    organization = orm.relationship("Organization", lazy=False)
    customer = orm.relationship("StripeCustomer", lazy=False)


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

    name = mapped_column(Text, nullable=False, comment="The account name used in URLS")

    @declared_attr
    def normalized_name(cls):  # noqa: N805
        return orm.column_property(func.normalize_pep426_name(cls.name))

    display_name = mapped_column(
        Text, nullable=False, comment="Display name used in UI"
    )
    orgtype = mapped_column(
        Enum(OrganizationType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        comment="What type of organization such as Community or Company",
    )
    link_url = mapped_column(
        Text, nullable=False, comment="External URL associated with the organization"
    )
    description = mapped_column(
        Text,
        nullable=False,
        comment="Description of the business or project the organization represents",
    )

    is_approved = mapped_column(
        Boolean, comment="Status of administrator approval of the request"
    )


# TODO: Determine if this should also utilize SitemapMixin and TwoFactorRequireable
# class Organization(SitemapMixin, TwoFactorRequireable, HasEvents, db.Model):
class Organization(OrganizationMixin, HasEvents, db.Model):
    __tablename__ = "organizations"

    __repr__ = make_repr("name")

    is_active = mapped_column(
        Boolean,
        nullable=False,
        server_default=sql.false(),
        comment="When True, the organization is active and all features are available.",
    )
    created = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=sql.func.now(),
        index=True,
        comment="Datetime the organization was created.",
    )
    date_approved = mapped_column(
        DateTime(timezone=False),
        nullable=True,
        onupdate=func.now(),
        comment="Datetime the organization was approved by administrators.",
    )

    users = orm.relationship(
        User, secondary=OrganizationRole.__table__, backref="organizations", viewonly=True  # type: ignore # noqa
    )
    teams = orm.relationship(
        "Team",
        back_populates="organization",
        order_by=lambda: Team.name.asc(),  # type: ignore
    )
    projects = orm.relationship(
        "Project", secondary=OrganizationProject.__table__, back_populates="organization", viewonly=True  # type: ignore # noqa
    )
    customer = orm.relationship(
        "StripeCustomer", secondary=OrganizationStripeCustomer.__table__, back_populates="organization", uselist=False, viewonly=True  # type: ignore # noqa
    )
    subscriptions = orm.relationship(
        "StripeSubscription", secondary=OrganizationStripeSubscription.__table__, back_populates="organization", viewonly=True  # type: ignore # noqa
    )

    @property
    def owners(self):
        """Return all users who are owners of the organization."""
        owner_roles = (
            orm.object_session(self)
            .query(User.id)
            .join(OrganizationRole.user)
            .filter(
                OrganizationRole.role_name == OrganizationRoleType.Owner,
                OrganizationRole.organization == self,
            )
            .subquery()
        )
        return (
            orm.object_session(self)
            .query(User)
            .join(owner_roles, User.id == owner_roles.c.id)
            .all()
        )

    def record_event(self, *, tag, request: Request = None, additional=None):
        """Record organization name in events in case organization is ever deleted."""
        super().record_event(
            tag=tag,
            request=request,
            additional={"organization_name": self.name, **additional},
        )

    def __acl__(self):
        session = orm.object_session(self)

        acls = [
            (Allow, "group:admins", "admin"),
            (Allow, "group:moderators", "moderator"),
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
                # - View organization ("view:organization")
                # - View team ("view:team")
                # - Invite/remove organization member ("manage:organization")
                # - Create/delete team and add/remove team member ("manage:team")
                # - Manage billing ("manage:billing")
                # - Add project ("add:project")
                # - Remove project ("remove:project")
                # Disallowed:
                # - (none)
                acls.append(
                    (
                        Allow,
                        f"user:{role.user.id}",
                        [
                            "view:organization",
                            "view:team",
                            "manage:organization",
                            "manage:team",
                            "manage:billing",
                            "add:project",
                            "remove:project",
                        ],
                    )
                )
            elif role.role_name == OrganizationRoleType.BillingManager:
                # Allowed:
                # - View organization ("view:organization")
                # - View team ("view:team")
                # - Manage billing ("manage:billing")
                # Disallowed:
                # - Invite/remove organization member ("manage:organization")
                # - Create/delete team and add/remove team member ("manage:team")
                # - Add project ("add:project")
                # - Remove project ("remove:project")
                acls.append(
                    (
                        Allow,
                        f"user:{role.user.id}",
                        ["view:organization", "view:team", "manage:billing"],
                    )
                )
            elif role.role_name == OrganizationRoleType.Manager:
                # Allowed:
                # - View organization ("view:organization")
                # - View team ("view:team")
                # - Create/delete team and add/remove team member ("manage:team")
                # - Add project ("add:project")
                # Disallowed:
                # - Invite/remove organization member ("manage:organization")
                # - Manage billing ("manage:billing")
                # - Remove project ("remove:project")
                acls.append(
                    (
                        Allow,
                        f"user:{role.user.id}",
                        [
                            "view:organization",
                            "view:team",
                            "manage:team",
                            "add:project",
                        ],
                    )
                )
            else:
                # No member-specific write access needed for now.

                # Allowed:
                # - View organization ("view:organization")
                # - View team ("view:team")
                # Disallowed:
                # - Invite/remove organization member ("manage:organization")
                # - Create/delete team and add/remove team member ("manage:team")
                # - Manage billing ("manage:billing")
                # - Add project ("add:project")
                # - Remove project ("remove:project")
                acls.append(
                    (Allow, f"user:{role.user.id}", ["view:organization", "view:team"])
                )
        return acls

    @property
    def active_subscription(self):
        for subscription in self.subscriptions:
            if not subscription.is_restricted:
                return subscription
        else:
            return None

    def customer_name(self, site_name="PyPI"):
        return f"{site_name} Organization - {self.display_name} ({self.name})"


class OrganizationApplication(OrganizationMixin, db.Model):
    __tablename__ = "organization_applications"
    __repr__ = make_repr("name")

    submitted_by_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            User.id,
            deferrable=True,
            initially="DEFERRED",
            ondelete="CASCADE",
        ),
        nullable=False,
        comment="ID of the User which submitted the request",
    )
    submitted = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=sql.func.now(),
        index=True,
        comment="Datetime the request was submitted",
    )
    organization_id = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            Organization.id,
            deferrable=True,
            initially="DEFERRED",
            ondelete="CASCADE",
        ),
        nullable=True,
        comment="If the request was approved, ID of resulting Organization",
    )

    submitted_by = orm.relationship(
        User, backref="organization_applications"  # type: ignore # noqa
    )
    organization = orm.relationship(
        Organization, backref="application", viewonly=True  # type: ignore # noqa
    )


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
    )

    __repr__ = make_repr("normalized_name", "organization_id")

    normalized_name = mapped_column(Text, nullable=False, index=True)
    organization_id = mapped_column(UUID(as_uuid=True), nullable=True, index=True)


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

    invite_status = mapped_column(
        Enum(
            OrganizationInvitationStatus, values_callable=lambda x: [e.value for e in x]
        ),
        nullable=False,
    )
    token = mapped_column(Text, nullable=False)
    user_id = mapped_column(
        ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id = mapped_column(
        ForeignKey("organizations.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user = orm.relationship(User, lazy=False)
    organization = orm.relationship("Organization", lazy=False)


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

    role_name = mapped_column(
        Enum(TeamRoleType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    user_id = mapped_column(
        ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False
    )
    team_id = mapped_column(
        ForeignKey("teams.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )

    user = orm.relationship(User, lazy=False)
    team = orm.relationship("Team", lazy=False)


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

    role_name = mapped_column(
        Enum(TeamProjectRoleType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    project_id = mapped_column(
        ForeignKey("projects.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    team_id = mapped_column(
        ForeignKey("teams.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )

    project = orm.relationship(
        "Project",
        lazy=False,
        back_populates="team_project_roles",
    )
    team = orm.relationship(
        "Team",
        lazy=False,
    )


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

    name = mapped_column(Text, nullable=False)
    normalized_name = orm.column_property(func.normalize_team_name(name))  # type: ignore[var-annotated] # noqa: E501
    organization_id = mapped_column(
        ForeignKey("organizations.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    created = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=sql.func.now(),
        index=True,
    )

    organization = orm.relationship("Organization", lazy=False, back_populates="teams")
    members = orm.relationship(
        User, secondary=TeamRole.__table__, backref="teams", viewonly=True  # type: ignore # noqa
    )
    projects = orm.relationship(
        "Project", secondary=TeamProjectRole.__table__, backref="teams", viewonly=True  # type: ignore # noqa
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
