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

from sqlalchemy import func
from sqlalchemy.orm.exc import NoResultFound
from zope.interface import implementer

from warehouse.accounts.models import User
from warehouse.organizations.interfaces import IOrganizationService
from warehouse.organizations.models import (
    Organization,
    OrganizationInvitation,
    OrganizationInvitationStatus,
    OrganizationNameCatalog,
    OrganizationProject,
    OrganizationRole,
)

NAME_FIELD = "name"


@implementer(IOrganizationService)
class DatabaseOrganizationService:
    def __init__(self, db_session, remote_addr):
        self.db = db_session
        self.remote_addr = remote_addr

    def get_organization(self, organization_id):
        """
        Return the organization object that represents the given organizationid,
        or None if there is no organization for that ID.
        """
        return self.db.query(Organization).get(organization_id)

    def get_organization_by_name(self, name):
        """
        Return the organization object corresponding with the given organization name,
        or None if there is no organization with that name.
        """
        organization_id = self.find_organizationid(name)
        return (
            None if organization_id is None else self.get_organization(organization_id)
        )

    def find_organizationid(self, name):
        """
        Find the unique organization identifier for the given normalized name or None
        if there is no organization with the given name.
        """
        normalized_name = func.normalize_pep426_name(name)
        try:
            organization = (
                self.db.query(Organization.id)
                .filter(Organization.normalized_name == normalized_name)
                .one()
            )
        except NoResultFound:
            return

        return organization.id

    def get_organizations(self):
        """
        Return a list of all organization objects, or None if there are none.
        """
        return self.db.query(Organization).order_by(Organization.name).all()

    def get_organizations_needing_approval(self):
        """
        Return a list of all organization objects in need of approval or None
        if there are currently no organization requests.
        """
        return (
            self.db.query(Organization)
            .filter(Organization.is_approved == None)  # noqa: E711
            .order_by(Organization.name)
            .all()
        )

    def get_organizations_by_user(self, user_id):
        """
        Return a list of all organization objects associated with a given user id.
        """
        return (
            self.db.query(Organization)
            .join(OrganizationRole, OrganizationRole.organization_id == Organization.id)
            .filter(OrganizationRole.user_id == user_id)
            .order_by(Organization.name)
            .all()
        )

    def add_organization(self, name, display_name, orgtype, link_url, description):
        """
        Accepts a organization object, and attempts to create an organization with those
        attributes.
        """
        organization = Organization(
            name=name,
            display_name=display_name,
            orgtype=orgtype,
            link_url=link_url,
            description=description,
        )
        self.db.add(organization)
        self.db.flush()

        return organization

    def add_catalog_entry(self, organization_id):
        """
        Adds the organization name to the organization name catalog
        """
        organization = self.get_organization(organization_id)
        catalog_entry = OrganizationNameCatalog(
            normalized_name=organization.normalized_name,
            organization_id=organization.id,
        )

        self.db.add(catalog_entry)
        self.db.flush()

        return catalog_entry

    def get_organization_role(self, organization_role_id):
        """
        Return the org role object that represents the given org role id,
        or None if there is no organization role for that ID.
        """
        return self.db.query(OrganizationRole).get(organization_role_id)

    def get_organization_role_by_user(self, organization_id, user_id):
        """
        Gets an organization role for a specified org and user
        """
        try:
            organization_role = (
                self.db.query(OrganizationRole)
                .filter(
                    OrganizationRole.organization_id == organization_id,
                    OrganizationRole.user_id == user_id,
                )
                .one()
            )
        except NoResultFound:
            return

        return organization_role

    def get_organization_roles(self, organization_id):
        """
        Gets a list of organization roles for a specified org
        """
        return (
            self.db.query(OrganizationRole)
            .join(User)
            .filter(OrganizationRole.organization_id == organization_id)
            .all()
        )

    def add_organization_role(self, organization_id, user_id, role_name):
        """
        Adds an organization role for the specified org and user
        """
        role = OrganizationRole(
            organization_id=organization_id,
            user_id=user_id,
            role_name=role_name,
        )

        self.db.add(role)
        self.db.flush()

        return role

    def delete_organization_role(self, organization_role_id):
        """
        Delete an organization role for a specified organization role id
        """
        role = self.get_organization_role(organization_role_id)

        self.db.delete(role)
        self.db.flush()

    def get_organization_invite(self, organization_invite_id):
        """
        Return the org invite object that represents the given org invite id,
        or None if there is no organization invite for that ID.
        """
        return self.db.query(OrganizationInvitation).get(organization_invite_id)

    def get_organization_invite_by_user(self, organization_id, user_id):
        """
        Gets an organization invite for a specified org and user
        """
        try:
            organization_invite = (
                self.db.query(OrganizationInvitation)
                .filter(
                    OrganizationInvitation.organization_id == organization_id,
                    OrganizationInvitation.user_id == user_id,
                )
                .one()
            )
        except NoResultFound:
            return

        return organization_invite

    def get_organization_invites(self, organization_id):
        """
        Gets a list of organization invites for a specified org
        """
        return (
            self.db.query(OrganizationInvitation)
            .join(User)
            .filter(OrganizationInvitation.organization_id == organization_id)
            .all()
        )

    def get_organization_invites_by_user(self, user_id):
        """
        Gets a list of organization invites for a specified user
        """
        return (
            self.db.query(OrganizationInvitation)
            .filter(
                OrganizationInvitation.invite_status
                == OrganizationInvitationStatus.Pending,
                OrganizationInvitation.user_id == user_id,
            )
            .all()
        )

    def add_organization_invite(self, organization_id, user_id, invite_token):
        """
        Adds an organization invitation for the specified user and org
        """
        # organization = self.get_organization(organization_id)
        organization_invite = OrganizationInvitation(
            organization_id=organization_id,
            user_id=user_id,
            token=invite_token,
            invite_status=OrganizationInvitationStatus.Pending,
        )

        self.db.add(organization_invite)
        self.db.flush()

        return organization_invite

    def delete_organization_invite(self, organization_invite_id):
        """
        Delete an organization invite for the specified org invite id
        """
        organization_invite = self.get_organization_invite(organization_invite_id)

        self.db.delete(organization_invite)
        self.db.flush()

    def approve_organization(self, organization_id):
        """
        Performs operations necessary to approve an Organization
        """
        organization = self.get_organization(organization_id)
        organization.is_active = True
        organization.is_approved = True
        organization.date_approved = datetime.datetime.now()
        # self.db.flush()

        return organization

    def decline_organization(self, organization_id):
        """
        Performs operations necessary to reject approval of an Organization
        """
        organization = self.get_organization(organization_id)
        organization.is_active = False
        organization.is_approved = False
        organization.date_approved = datetime.datetime.now()
        # self.db.flush()

        return organization

    def delete_organization(self, organization_id):
        """
        Delete an organization for the specified organization id
        """
        organization = self.get_organization(organization_id)

        # Delete invitations
        self.db.query(OrganizationInvitation).filter_by(
            organization=organization
        ).delete()
        # Null out organization id for all name catalog entries
        self.db.query(OrganizationNameCatalog).filter(
            OrganizationNameCatalog.organization_id == organization_id
        ).update({OrganizationNameCatalog.organization_id: None})
        # Delete projects
        self.db.query(OrganizationProject).filter_by(organization=organization).delete()
        # Delete roles
        self.db.query(OrganizationRole).filter_by(organization=organization).delete()
        # TODO: Delete any stored card data from payment processor
        # Delete organization
        self.db.delete(organization)
        self.db.flush()

    def rename_organization(self, organization_id, name):
        """
        Performs operations necessary to rename an Organization
        """
        organization = self.get_organization(organization_id)

        organization.name = name
        self.db.flush()

        self.add_catalog_entry(organization_id)

        return organization

    def update_organization(self, organization_id, **changes):
        """
        Accepts a organization object and attempts to update an organization with those
        attributes
        """
        organization = self.get_organization(organization_id)
        for attr, value in changes.items():
            if attr == NAME_FIELD:
                # Call rename function to ensure name catalag entry is added
                self.rename_organization(organization_id, value)
            setattr(organization, attr, value)

        return organization

    def record_event(self, organization_id, *, tag, additional=None):
        """
        Creates a new Organization.Event for the given organization with the given
        tag, IP address, and additional metadata.

        Returns the event.
        """
        organization = self.get_organization(organization_id)
        return organization.record_event(
            tag=tag, ip_address=self.remote_addr, additional=additional
        )


def database_organization_factory(context, request):
    return DatabaseOrganizationService(request.db, remote_addr=request.remote_addr)
