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

    def get_organizations():
        """
        Return a list of all organization objects, or None if there are none.
        """

    def get_organizations_needing_approval():
        """
        Return a list of all organization objects in need of approval or None
        if there are currently no organization requests.
        """

    def get_organizations_by_user(user_id):
        """
        Return a list of all organization objects associated with a given user id.
        """

    def add_organization(name, display_name, orgtype, link_url, description):
        """
        Accepts a organization object, and attempts to create an organization with those
        attributes.
        """

    def add_catalog_entry(organization_id):
        """
        Adds the organization name to the organization name catalog
        """

    def get_organization_role(organization_role_id):
        """
        Return the org role object that represents the given org role id,
        or None if there is no organization role for that ID.
        """

    def get_organization_role_by_user(organization_id, user_id):
        """
        Gets an organization role for a specified org and user
        """

    def get_organization_roles(organization_id):
        """
        Gets a list of organization roles for a specified org
        """

    def add_organization_role(organization_id, user_id, role_name):
        """
        Adds an organization role for the specified org and user
        """

    def delete_organization_role(organization_role_id):
        """
        Delete an organization role for a specified organization role id
        """

    def get_organization_invite(organization_invite_id):
        """
        Return the org invite object that represents the given org invite id,
        or None if there is no organization invite for that ID.
        """

    def get_organization_invite_by_user(organization_id, user_id):
        """
        Gets an organization invite for a specified org and user
        """

    def get_organization_invites(organization_id):
        """
        Gets a list of organization invites for a specified org
        """

    def get_organization_invites_by_user(user_id):
        """
        Gets a list of organization invites for a specified user
        """

    def add_organization_invite(organization_id, user_id, invite_token):
        """
        Adds an organization invitation for the specified user and org
        """

    def delete_organization_invite(organization_invite_id):
        """
        Delete an organization invite for the specified org invite id
        """

    def approve_organization(organization_id):
        """
        Performs operations necessary to approve an organization
        """

    def decline_organization(organization_id):
        """
        Performs operations necessary to reject approval of an organization
        """

    def delete_organization(organization_id):
        """
        Delete an organization for the specified organization id
        """

    def rename_organization(organization_id, name):
        """
        Performs operations necessary to rename an Organization
        """

    def update_organization(organization_id, **changes):
        """
        Accepts a organization object and attempts to update an organization with those
        attributes
        """

    def record_event(organization_id, *, tag, additional=None):
        """
        Creates a new Organization.Event for the given organization with the given
        tag, IP address, and additional metadata.

        Returns the event.
        """
