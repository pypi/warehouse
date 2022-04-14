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

from sqlalchemy.orm.exc import NoResultFound
from zope.interface import implementer

from warehouse.organizations.interfaces import IOrganizationService
from warehouse.organizations.models import (
    Organization,
    OrganizationNameCatalog,
    OrganizationRole,
)


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
        Find the unique organization identifier for the given name or None if there
        is no organization with the given name.
        """
        try:
            organization = (
                self.db.query(Organization.id).filter(Organization.name == name).one()
            )
        except NoResultFound:
            return

        return organization.id

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

    def add_catalog_entry(self, name, organization_id):
        """
        Adds the organization name to the organization name catalog
        """
        organization = self.get_organization(organization_id)
        catalog_entry = OrganizationNameCatalog(
            name=name, organization_id=organization.id
        )

        self.db.add(catalog_entry)
        self.db.flush()

        return catalog_entry

    def add_organization_role(self, role_name, user_id, organization_id):
        """
        Adds the organization role to the specified user and org
        """
        organization = self.get_organization(organization_id)
        role = OrganizationRole(
            role_name=role_name, user_id=user_id, organization_id=organization.id
        )

        self.db.add(role)
        self.db.flush()

        return role

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
        organization.is_approved = False
        organization.date_approved = datetime.datetime.now()
        # self.db.flush()

        return organization

    def record_event(self, organization_id, *, tag, additional=None):
        """
        Creates a new OrganizationEvent for the given organization with the given
        tag, IP address, and additional metadata.

        Returns the event.
        """
        organization = self.get_organization(organization_id)
        return organization.record_event(
            tag=tag, ip_address=self.remote_addr, additional=additional
        )


def database_organization_factory(context, request):
    return DatabaseOrganizationService(request.db, remote_addr=request.remote_addr)
