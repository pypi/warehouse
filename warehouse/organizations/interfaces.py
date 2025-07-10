# SPDX-License-Identifier: Apache-2.0

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

    def get_organization_application(organization_application_id):
        """
        Return the organization application object that represents the given
        organization_application_id, or None if there is no organization application
        for that ID.
        """

    def get_organization_applications_by_name(name):
        """
        Return any organization application object that represents the given name
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

    def get_organizations_by_user(user_id):
        """
        Return a list of all organization objects associated with a given user id.
        """

    def approve_organization_application(organization_application_id, request):
        """
        Performs operations necessary to approve an organization
        """

    def decline_organization_application(organization_application_id, request):
        """
        Performs operations necessary to reject approval of an organization
        """

    def add_organization_application(
        name,
        display_name,
        orgtype,
        link_url,
        description,
        usage,
        membership_size,
        submitted_by,
    ):
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

    def get_organization_project(organization_id, project_id):
        """
        Return the organization project object that represents the given
        organization and project or None
        """

    def add_organization_project(organization_id, project_id):
        """
        Adds an association between the specified organization and project
        """

    def delete_organization_project(organization_id, project_id):
        """
        Removes an association between the specified organization and project
        """

    def record_tos_engagement(
        organization_id,
        revision,
        engagement,
    ):
        """
        Add a record of end user agreeing to terms of service,
        or being notified of a terms of service change.
        """

    def get_organization_subscription(organization_id, subscription_id):
        """
        Return the organization subscription object that represents the given
        organization subscription id or None
        """

    def add_organization_subscription(organization_id, subscription_id):
        """
        Adds an association between the specified organization and subscription
        """

    def delete_organization_subscription(organization_id, subscription_id):
        """
        Delete association between specified organization and subscription
        """

    def get_organization_stripe_customer(organization_id):
        """
        Return the organization stripe customer object that is
        associated to the given organization id or None
        """

    def add_organization_stripe_customer(organization_id, stripe_customer_id):
        """
        Adds an association between the specified organization and customer
        """

    def get_teams_by_organization(organization_id):
        """
        Return a list of all team objects for the specified organization,
        or None if there are none.
        """

    def get_team(team_id):
        """
        Return a team object for the specified identifier,
        """

    def find_teamid(organization_id, team_name):
        """
        Find the unique team identifier for the given organization and
        team name or None if there is no such team.
        """

    def get_teams_by_user(user_id):
        """
        Return a list of all team objects associated with a given user id.
        """

    def add_team(organization_id, name):
        """
        Attempts to create a team with the specified name in an organization
        """

    def rename_team(team_id, name):
        """
        Performs operations necessary to rename a Team
        """

    def delete_team(team_id):
        """
        Delete team for the specified team id and all associated objects
        """

    def delete_teams_by_organization(organization_id):
        """
        Delete all teams for the specified organization id
        """

    def get_team_role(team_role_id):
        """
        Return the team role object that represents the given team role id,
        """

    def add_team_role(team_id, user_id, role_name):
        """
        Add the team role object to a team for a specified team id and user id
        """

    def delete_team_role(team_role_id):
        """
        Remove the team role for a specified team id and user id
        """

    def get_team_project_role(team_project_role_id):
        """
        Return the team project role object that represents the given team project role id,
        """

    def add_team_project_role(team_id, project_id, role_name):
        """
        Adds a team project role for the specified team and project
        """

    def delete_team_project_role(team_project_role_id):
        """
        Delete an team project role for a specified team project role id
        """
