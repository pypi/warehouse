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
    Team,
    TeamProjectRole,
    TeamRole,
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
            (organization_id,) = (
                self.db.query(OrganizationNameCatalog.organization_id)
                .filter(OrganizationNameCatalog.normalized_name == normalized_name)
                .one()
            )
        except NoResultFound:
            return

        return organization_id

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
        # Delete teams (and related data)
        self.delete_teams_by_organization(organization_id)
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

    def get_organization_project(self, organization_id, project_id):
        """
        Return the organization project object that represents the given
        organization project id or None
        """
        return (
            self.db.query(OrganizationProject)
            .filter(
                OrganizationProject.organization_id == organization_id,
                OrganizationProject.project_id == project_id,
            )
            .first()
        )

    def add_organization_project(self, organization_id, project_id):
        """
        Adds an association between the specified organization and project
        """
        organization_project = OrganizationProject(
            organization_id=organization_id,
            project_id=project_id,
        )

        self.db.add(organization_project)
        self.db.flush()

        return organization_project

    def delete_organization_project(self, organization_id, project_id):
        """
        Performs soft delete of association between specified organization and project
        """
        organization_project = self.get_organization_project(
            organization_id, project_id
        )

        self.db.delete(organization_project)
        self.db.flush()

    def get_teams_by_organization(self, organization_id):
        """
        Return a list of all team objects for the specified organization,
        or None if there are none.
        """
        return self.db.query(Team).filter(Team.organization_id == organization_id).all()

    def get_team(self, team_id):
        """
        Return a team object for the specified identifier,
        """
        return self.db.query(Team).get(team_id)

    def find_teamid(self, organization_id, team_name):
        """
        Find the unique team identifier for the given organization and
        team name or None if there is no such team.
        """
        normalized_name = func.normalize_team_name(team_name)
        try:
            (team_id,) = (
                self.db.query(Team.id)
                .filter(
                    Team.organization_id == organization_id,
                    Team.normalized_name == normalized_name,
                )
                .one()
            )
        except NoResultFound:
            return

        return team_id

    def get_teams_by_user(self, user_id):
        """
        Return a list of all team objects associated with a given user id.
        """
        return (
            self.db.query(Team)
            .join(TeamRole, TeamRole.team_id == Team.id)
            .filter(TeamRole.user_id == user_id)
            .order_by(Team.name)
            .all()
        )

    def add_team(self, organization_id, name):
        """
        Attempts to create a team with the specified name in an organization
        """
        team = Team(
            name=name,
            organization_id=organization_id,
        )
        self.db.add(team)
        self.db.flush()

        return team

    def rename_team(self, team_id, name):
        """
        Performs operations necessary to rename a Team
        """
        team = self.get_team(team_id)

        team.name = name
        self.db.flush()

        return team

    def delete_team(self, team_id):
        """
        Delete team for the specified team id and all associated objects
        """
        team = self.get_team(team_id)
        # Delete team members
        self.db.query(TeamRole).filter_by(team=team).delete()
        # Delete projects
        self.db.query(TeamProjectRole).filter_by(team=team).delete()
        # Delete team
        self.db.delete(team)
        self.db.flush()

    def delete_teams_by_organization(self, organization_id):
        """
        Delete all teams for the specified organization id
        """
        teams = self.get_teams_by_organization(organization_id)
        for team in teams:
            self.delete_team(team.id)

    def get_team_role(self, team_role_id):
        """
        Return the team role object that represents the given team role id,
        """
        return self.db.query(TeamRole).get(team_role_id)

    def get_team_role_by_user(self, team_id, user_id):
        """
        Gets a team role for a specified team and user
        """
        try:
            team_role = (
                self.db.query(TeamRole)
                .filter(
                    TeamRole.team_id == team_id,
                    TeamRole.user_id == user_id,
                )
                .one()
            )
        except NoResultFound:
            return

        return team_role

    def get_team_roles(self, team_id):
        """
        Gets a list of organization roles for a specified org
        """
        return (
            self.db.query(TeamRole).join(User).filter(TeamRole.team_id == team_id).all()
        )

    def add_team_role(self, team_id, user_id, role_name):
        """
        Add the team role object to a team for a specified team id and user id
        """
        member = TeamRole(
            team_id=team_id,
            user_id=user_id,
            role_name=role_name,
        )

        self.db.add(member)
        self.db.flush()

        return member

    def delete_team_role(self, team_role_id):
        """
        Remove the team role for a specified team id and user id
        """
        member = self.get_team_role(team_role_id)

        self.db.delete(member)
        self.db.flush()

    def get_team_project_role(self, team_project_role_id):
        """
        Return the team project role object that
        represents the given team project role id,
        """
        return self.db.query(TeamProjectRole).get(team_project_role_id)

    def add_team_project_role(self, team_id, project_id, role_name):
        """
        Adds a team project role for the specified team and project
        """
        team_project_role = TeamProjectRole(
            team_id=team_id,
            project_id=project_id,
            role_name=role_name,
        )

        self.db.add(team_project_role)
        self.db.flush()

        return team_project_role

    def delete_team_project_role(self, team_project_role_id):
        """
        Remove a team project role for a specified team project role id
        """
        team_project_role = self.get_team_project_role(team_project_role_id)

        self.db.delete(team_project_role)
        self.db.flush()

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
