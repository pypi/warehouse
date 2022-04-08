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

from collections import OrderedDict
from urllib.parse import urlparse

import packaging.utils

from citext import CIText
from pyramid.authorization import Allow
from pyramid.threadlocal import get_current_request
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    orm,
    sql,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declared_attr  # type: ignore
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import validates
from sqlalchemy.orm.exc import MultipleResultsFound, NoResultFound
from sqlalchemy.sql import expression
from sqlalchemy_utils.types.url import URLType
from trove_classifiers import sorted_classifiers

from warehouse import db
from warehouse.accounts.models import User
from warehouse.classifiers.models import Classifier
from warehouse.integrations.vulnerabilities.models import VulnerabilityRecord
from warehouse.sitemap.models import SitemapMixin
from warehouse.utils import dotted_navigator
from warehouse.utils.attrs import make_repr
# TODO: Cleanup unused imports

class OrganizationFactory:
    def __init__(self, request):
        self.request = request

    def __getitem__(self, organization):
        try:
            return (
                self.request.db.query(Organization)
                .filter(Organization.name == organization)
                .one()
            )
        except NoResultFound:
            raise KeyError from None


#TODO: Determine if this should also utilize SitemapMixin and TwoFactorRequireable
#class Project(SitemapMixin, TwoFactorRequireable, db.Model):
class Organization(db.Model):
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
    orgtype = Column(Text, nullable=False)
    url = Column(URLType, nullable=False)
    desc = Column(Text, nullable=False)
    is_active = Column(Boolean)
    created = Column(
        DateTime(timezone=False),
        nullable=False,
        server_default=sql.func.now(),
        index=True,
    )
    
    # TODO: Determine if cascade applies to any of these relationships 
    users = orm.relationship(User, secondary=OrganizationRole.__table__, backref="organizations") # many-to-many
    projects = orm.relationship("Project", secondary=OrganizationProject.__table__, backref="organizations") # many-to-many
    #teams = orm.relationship("Team", primaryjoin=lambda: sql.and_(Team.organization_id == Organization.id), backref="organizations") # one-to-many
    #teams = orm.relationship("Team", primaryjoin="and_(Organization.id==Team.organization_id", backref="organizations") # one-to-many

# TODO:
#    def __getitem__(self, name): ???
#    def __acl__(self): 
# Do we want any properties?

class OrganizationNameCatalog(db.Model):

    __tablename__ = "organization_name_catalog"
    __table_args__ = (
        Index("organization_name_catalog_name_idx", "name"),
        Index("organization_name_catalog_organization_id_idx", "organization_id"),
        UniqueConstraint("name", "organization_id", name="_organization_name_catalog_name_organization_uc"),
    )

    __repr__ = make_repr("name", "organization_id")

    name = Column(Text, nullable=False)
    organization_id = Column(
        ForeignKey("organizations.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )

class OrganizationRole(db.Model):

    __tablename__ = "organization_roles"
    __table_args__ = (
        Index("organization_roles_user_id_idx", "user_id"),
        Index("organization_roles_organization_id_idx", "organization_id"),
        UniqueConstraint("user_id", "organization_id", name="_organization_roles_user_organization_uc"),
    )

    __repr__ = make_repr("role_name")

    role_name = Column(Text, nullable=False)
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
        UniqueConstraint("organization_id", "project_id", name="_organization_project_organization_project_uc"),
    )

    __repr__ = make_repr("project_id", "organization_id", "is_active")

    is_active = Column(Boolean)
    organization_id = Column(
        ForeignKey("organizations.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False
    )
    project_id = Column(
        ForeignKey("projects.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )

    organization = orm.relationship("Organization", lazy=False)
    project = orm.relationship("Project", lazy=False)

class OrganizationInvitationStatus(enum.Enum):

    Pending = "pending"
    Expired = "expired"


class OrganizationInvitation(db.Model):

    __tablename__ = "organization_invitations"
    __table_args__ = (
        Index("organization_invitations_user_id_idx", "user_id"),
        UniqueConstraint(
            "user_id", "organization_id", name="_organization_invitations_user_organization_uc"
        ),
    )

    __repr__ = make_repr("invite_status", "user", "organization")

    invite_status = Column(
        Enum(OrganizationInvitationStatus, values_callable=lambda x: [e.value for e in x]),
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