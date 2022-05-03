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

from pyramid.authorization import Allow
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
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
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy_utils.types.url import URLType

from warehouse import db
from warehouse.accounts.models import User
from warehouse.events.models import HasEvents
from warehouse.utils.attrs import make_repr


class OrganizationRoleType(enum.Enum):

    BillingManager = "Billing Manager"
    Manager = "Manager"
    Member = "Member"
    Owner = "Owner"


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

    role_name = Column(
        Enum(OrganizationRoleType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    user_id = Column(
        ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False
    )
    organization_id = Column(
        ForeignKey("organizations.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )

    user = orm.relationship(User, lazy=False)
    organization = orm.relationship("Organization", lazy=False)


class OrganizationProject(db.Model):

    __tablename__ = "organization_project"
    __table_args__ = (
        Index("organization_project_organization_id_idx", "organization_id"),
        Index("organization_project_project_id_idx", "project_id"),
        UniqueConstraint(
            "organization_id",
            "project_id",
            name="_organization_project_organization_project_uc",
        ),
    )

    __repr__ = make_repr("project_id", "organization_id", "is_active")

    is_active = Column(Boolean, nullable=False, server_default=sql.false())
    organization_id = Column(
        ForeignKey("organizations.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    project_id = Column(
        ForeignKey("projects.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )

    organization = orm.relationship("Organization", lazy=False)
    project = orm.relationship("Project", lazy=False)


class OrganizationType(enum.Enum):

    Community = "Community"
    Company = "Company"


class OrganizationFactory:
    def __init__(self, request):
        self.request = request

    def __getitem__(self, organization):
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
            raise KeyError from None


# TODO: Determine if this should also utilize SitemapMixin and TwoFactorRequireable
# class Organization(SitemapMixin, TwoFactorRequireable, HasEvents, db.Model):
class Organization(HasEvents, db.Model):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(
            "name ~* '^([A-Z0-9]|[A-Z0-9][A-Z0-9._-]*[A-Z0-9])$'::text",
            name="organizations_valid_name",
        ),
    )

    __repr__ = make_repr("name")

    name = Column(Text, nullable=False)
    normalized_name = orm.column_property(func.normalize_pep426_name(name))
    display_name = Column(Text, nullable=False)
    orgtype = Column(
        Enum(OrganizationType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    link_url = Column(URLType, nullable=False)
    description = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, server_default=sql.false())
    is_approved = Column(Boolean)
    created = Column(
        DateTime(timezone=False),
        nullable=False,
        server_default=sql.func.now(),
        index=True,
    )
    date_approved = Column(
        DateTime(timezone=False),
        nullable=True,
        onupdate=func.now(),
    )

    users = orm.relationship(
        User, secondary=OrganizationRole.__table__, backref="organizations"  # type: ignore # noqa
    )
    projects = orm.relationship(
        "Project", secondary=OrganizationProject.__table__, backref="organizations"  # type: ignore # noqa
    )

    def __acl__(self):
        session = orm.object_session(self)

        # TODO: The "group:admins" and "group:moderators" principals
        #           automatically get granted permissions in projects
        #       Should do something similar in organizations?

        # acls = [
        #     (Allow, "group:admins", "manage:organization"),
        #     (Allow, "group:moderators", "manage:team"),
        # ]

        acls = []

        # Get all of the users for this organization.
        query = session.query(OrganizationRole).filter(
            OrganizationRole.organization == self
        )
        query = query.options(orm.lazyload("organization"))
        query = query.join(User).order_by(User.id.asc())
        for role in sorted(
            query.all(),
            key=lambda x: [e.value for e in OrganizationRoleType].index(x.role_name),
        ):
            if role.role_name == OrganizationRoleType.Owner:
                acls.append((Allow, f"user:{role.user.id}", ["manage:organization"]))
            elif role.role_name == OrganizationRoleType.BillingManager:
                acls.append((Allow, f"user:{role.user.id}", ["manage:billing"]))
            elif role.role_name == OrganizationRoleType.Manager:
                acls.append((Allow, f"user:{role.user.id}", ["manage:team"]))
            else:  # TODO Member: Do we need this? May be covered by Project acl?
                acls.append((Allow, f"user:{role.user.id}", ["organization:member"]))
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
    )

    __repr__ = make_repr("normalized_name", "organization_id")

    normalized_name = Column(Text, nullable=False)
    organization_id = Column(
        ForeignKey("organizations.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )


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

    invite_status = Column(
        Enum(
            OrganizationInvitationStatus, values_callable=lambda x: [e.value for e in x]
        ),
        nullable=False,
    )
    token = Column(Text, nullable=False)
    user_id = Column(
        ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id = Column(
        ForeignKey("organizations.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user = orm.relationship(User, lazy=False)
    organization = orm.relationship("Organization", lazy=False)
