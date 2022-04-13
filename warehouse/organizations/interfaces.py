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

from zope.interface import Interface


class IOrganizationService(Interface):
    def get_organization(organization_id):
        """
        Return the organization object that represents the given organizationid, or None if
        there is no organization for that ID.
        """

    def get_organization_by_name(name):
        """
        Return the organization object corresponding with the given organization name, or None
        if there is no organization with that name.
        """

    def find_organizationid(name):
        """
        Find the unique organization identifier for the given name or None if there
        is no organization with the given name.
        """

    def add_organization(name, display_name, orgtype, link_url, description):
        """
        Accepts a organization object, and attempts to create an organization with those
        attributes.
        """

    def add_catalog_entry(name, organization_id):
        """
        Adds the organization name to the organization name catalog
        """

    def add_organization_role(role_name, user_id, organization_id):
        """
        Adds the organization role to the specified user and org
        """

    def approve_organization(organization_id):
        """
        Performs operations necessary to approve an organization
        """

    def decline_organization(organization_id):
        """
        Performs operations necessary to reject approval of an organization
        """

    def record_event(organization_id, *, tag, additional=None):
        """
        Creates a new OrganizationEvent for the given organization with the given
        tag, IP address, and additional metadata.

        Returns the event.
        """
