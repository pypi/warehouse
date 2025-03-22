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

from sqlalchemy import delete, func, orm, select
from sqlalchemy.exc import NoResultFound
from zope.interface import implementer

from warehouse.accounts.models import TermsOfServiceEngagement, User
from warehouse.email import (
    send_new_organization_approved_email,
    send_new_organization_declined_email,
    send_new_organization_moreinformationneeded_email,
)
from warehouse.events.tags import EventTag
from warehouse.observations.models import ObservationKind
from warehouse.organizations.interfaces import IOrganizationService
from warehouse.organizations.models import (
    Organization,
    OrganizationApplication,
    OrganizationApplicationStatus,
    OrganizationInvitation,
    OrganizationInvitationStatus,
    OrganizationNameCatalog,
    OrganizationProject,
    OrganizationRole,
    OrganizationRoleType,
    OrganizationStripeCustomer,
    OrganizationStripeSubscription,
    OrganizationTermsOfServiceEngagement,
    Team,
    TeamProjectRole,
    TeamRole,
)
from warehouse.subscriptions.models import StripeSubscription, StripeSubscriptionItem

NAME_FIELD = "name"


@implementer(IOrganizationService)
class DatabaseOrganizationService:
    def __init__(self, db_session):
        self.db = db_session

    def get_organization(self, organization_id):
        """
        Return the organization object that represents the given organizationid,
        or None if there is no organization for that ID.
        """
        return self.db.get(Organization, organization_id)

    def get_organization_application(self, organization_application_id):
        """
        Return the organization application object that represents the given
        organization_application_id, or None if there is no application for that ID.
        """
        return self.db.get(OrganizationApplication, organization_application_id)

    def get_organization_by_name(self, name):
        """
        Return the organization object corresponding with the given organization name,
        or None if there is no organization with that name.
        """
        organization_id = self.find_organizationid(name)
        return (
            None if organization_id is None else self.get_organization(organization_id)
        )

    def get_organization_applications_by_name(
        self, name, submitted_by=None, undecided=False
    ):
        """
        Return the organization object corresponding with the given organization name,
        or None if there is no organization with that name.
        """
        normalized_name = func.normalize_pep426_name(name)
        query = self.db.query(OrganizationApplication).filter(
            OrganizationApplication.normalized_name == normalized_name
        )
        if submitted_by is not None:
            query = query.filter(OrganizationApplication.submitted_by == submitted_by)
        if undecided is True:
            query = query.filter(
                OrganizationApplication.status
                == (OrganizationApplicationStatus.Submitted)
            )
        return query.order_by(OrganizationApplication.normalized_name).all()

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
        return self.db.scalars(select(Organization).order_by(Organization.name)).all()

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

    def add_organization_application(
        self, name, display_name, orgtype, link_url, description, submitted_by
    ):
        """
        Accepts organization application details, creates an OrganizationApplication
        with those attributes.
        """
        organization_application = OrganizationApplication(
            name=name,
            display_name=display_name,
            orgtype=orgtype,
            link_url=link_url,
            description=description,
            submitted_by=submitted_by,
        )
        self.db.add(organization_application)

        return organization_application

    def approve_organization_application(self, organization_application_id, request):
        """
        Performs operations necessary to approve an OrganizationApplication
        """
        organization_application = self.get_organization_application(
            organization_application_id
        )

        organization = Organization(
            name=organization_application.name,
            display_name=organization_application.display_name,
            orgtype=organization_application.orgtype,
            link_url=organization_application.link_url,
            description=organization_application.description,
            is_active=True,
        )
        self.db.add(organization)
        organization.record_event(
            tag=EventTag.Organization.OrganizationCreate,
            request=request,
            additional={
                "created_by_user_id": str(organization_application.submitted_by.id),
                "redact_ip": True,
            },
        )
        self.db.flush()  # flush the db now so organization.id is available

        organization_application.status = OrganizationApplicationStatus.Approved
        organization_application.organization = organization

        self.add_catalog_entry(organization.id)
        organization.record_event(
            tag=EventTag.Organization.CatalogEntryAdd,
            request=request,
            additional={
                "submitted_by_user_id": str(organization_application.submitted_by.id),
                "redact_ip": True,
            },
        )

        self.add_organization_role(
            organization.id,
            organization_application.submitted_by.id,
            OrganizationRoleType.Owner,
        )
        organization.record_event(
            tag=EventTag.Organization.OrganizationRoleAdd,
            request=request,
            additional={
                "submitted_by_user_id": str(organization_application.submitted_by.id),
                "role_name": "Owner",
                "target_user_id": str(organization_application.submitted_by.id),
                "redact_ip": True,
            },
        )
        organization_application.submitted_by.record_event(
            tag=EventTag.Account.OrganizationRoleAdd,
            request=request,
            additional={
                "submitted_by_user_id": str(organization_application.submitted_by.id),
                "organization_name": organization.name,
                "role_name": "Owner",
                "redact_ip": True,
            },
        )
        organization.record_event(
            tag=EventTag.Organization.OrganizationApprove,
            request=request,
            additional={"approved_by_user_id": str(request.user.id)},
        )

        message = request.params.get("message", "")
        send_new_organization_approved_email(
            request,
            organization_application.submitted_by,
            organization_name=organization.name,
            message=message,
        )

        for competing_application in self.get_organization_applications_by_name(
            organization_application.name, undecided=True
        ):
            self.decline_organization_application(competing_application.id, request)

        return organization

    def defer_organization_application(self, organization_application_id, request):
        """
        Performs operations necessary to defer an OrganizationApplication
        """
        organization_application = self.get_organization_application(
            organization_application_id
        )
        organization_application.status = OrganizationApplicationStatus.Deferred

        return organization_application

    def request_more_information(self, organization_application_id, request):
        """
        Performs operations necessary to request more information of an
        OrganizationApplication
        """
        organization_application = self.get_organization_application(
            organization_application_id
        )
        organization_application.status = (
            OrganizationApplicationStatus.MoreInformationNeeded
        )

        message = request.params.get("message", "")

        organization_application.record_observation(
            request=request,
            actor=request.user,
            summary="Organization request needs more information",
            kind=ObservationKind.InformationRequest,
            payload={"message": message},
        )
        send_new_organization_moreinformationneeded_email(
            request,
            organization_application.submitted_by,
            organization_name=organization_application.name,
            organization_application_id=organization_application.id,
            message=message,
        )

        return organization_application

    def decline_organization_application(self, organization_application_id, request):
        """
        Performs operations necessary to decline an OrganizationApplication
        """
        organization_application = self.get_organization_application(
            organization_application_id
        )
        organization_application.status = OrganizationApplicationStatus.Declined

        message = request.params.get("message", "")
        send_new_organization_declined_email(
            request,
            organization_application.submitted_by,
            organization_name=organization_application.name,
            message=message,
        )

        return organization_application

    def add_catalog_entry(self, organization_id):
        """
        Adds the organization name to the organization name catalog
        """
        organization = self.get_organization(organization_id)
        catalog_entry = OrganizationNameCatalog(
            normalized_name=organization.normalized_name,
            organization_id=organization.id,
        )

        try:
            # Check if this organization name has already been used
            catalog_entry = (
                self.db.query(OrganizationNameCatalog)
                .filter(
                    OrganizationNameCatalog.normalized_name
                    == organization.normalized_name,
                )
                .one()
            )
        except NoResultFound:
            self.db.add(catalog_entry)

        return catalog_entry

    def get_organization_role(self, organization_role_id):
        """
        Return the org role object that represents the given org role id,
        or None if there is no organization role for that ID.
        """
        return self.db.get(OrganizationRole, organization_role_id)

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

        return role

    def delete_organization_role(self, organization_role_id):
        """
        Delete an organization role for a specified organization role id
        """
        role = self.get_organization_role(organization_role_id)

        self.db.delete(role)

    def get_organization_invite(self, organization_invite_id):
        """
        Return the org invite object that represents the given org invite id,
        or None if there is no organization invite for that ID.
        """
        return self.db.get(OrganizationInvitation, organization_invite_id)

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

        return organization_invite

    def delete_organization_invite(self, organization_invite_id):
        """
        Delete an organization invite for the specified org invite id
        """
        organization_invite = self.get_organization_invite(organization_invite_id)

        self.db.delete(organization_invite)

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
        # Delete billing data if it exists
        if organization.subscriptions:
            for subscription in organization.subscriptions:
                # Delete subscription items
                self.db.query(StripeSubscriptionItem).filter_by(
                    subscription=subscription
                ).delete()
                # Delete link to organization
                self.db.query(OrganizationStripeSubscription).filter_by(
                    subscription=subscription
                ).delete()
                # Delete customer link to organization
                self.db.query(OrganizationStripeCustomer).filter_by(
                    organization=organization
                ).delete()
                # Delete subscription object
                self.db.query(StripeSubscription).filter(
                    StripeSubscription.id == subscription.id
                ).delete()
        # Delete teams (and related data)
        self.delete_teams_by_organization(organization_id)
        # Delete organization
        self.db.delete(organization)

    def rename_organization(self, organization_id, name):
        """
        Performs operations necessary to rename an Organization
        """
        organization = self.get_organization(organization_id)
        organization.name = name

        self.db.flush()  # flush db now so organization.normalized_name available
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
        self.db.flush()  # Flush db so we can address the organization related object

        # Mark Organization as dirty, so purges will happen
        orm.attributes.flag_dirty(organization_project.organization)

        return organization_project

    def delete_organization_project(self, organization_id, project_id):
        """
        Delete association between specified organization and project
        """
        organization_project = self.get_organization_project(
            organization_id, project_id
        )

        self.db.delete(organization_project)

    def record_tos_engagement(
        self,
        organization_id,
        revision: str,
        engagement: TermsOfServiceEngagement,
    ) -> None:
        """
        Add a record of end user being flashed about, notified of, viewing, or agreeing
        to a terms of service change on behalf of an organization.
        """
        if not isinstance(engagement, TermsOfServiceEngagement):
            raise ValueError(f"{engagement} is not a TermsOfServiceEngagement")
        self.db.add(
            OrganizationTermsOfServiceEngagement(
                organization_id=organization_id,
                revision=revision,
                created=datetime.datetime.now(datetime.UTC),
                engagement=engagement,
            )
        )

    def get_organization_subscription(self, organization_id, subscription_id):
        """
        Return the organization subscription object that represents the given
        organization subscription id or None
        """
        return (
            self.db.query(OrganizationStripeSubscription)
            .filter(
                OrganizationStripeSubscription.organization_id == organization_id,
                OrganizationStripeSubscription.subscription_id == subscription_id,
            )
            .first()
        )

    def add_organization_subscription(self, organization_id, subscription_id):
        """
        Adds an association between the specified organization and subscription
        """
        organization_subscription = OrganizationStripeSubscription(
            organization_id=organization_id,
            subscription_id=subscription_id,
        )

        self.db.add(organization_subscription)

        return organization_subscription

    def delete_organization_subscription(self, organization_id, subscription_id):
        """
        Delete association between specified organization and subscription
        """
        organization_subscription = self.get_organization_subscription(
            organization_id, subscription_id
        )

        self.db.delete(organization_subscription)

    def get_organization_stripe_customer(self, organization_id):
        """
        Return the organization stripe customer object that is
        associated to the given organization id or None
        """
        return (
            self.db.query(OrganizationStripeCustomer)
            .filter(
                OrganizationStripeCustomer.organization_id == organization_id,
            )
            .first()
        )

    def add_organization_stripe_customer(self, organization_id, stripe_customer_id):
        """
        Adds an association between the specified organization and customer
        """
        organization_stripe_customer = OrganizationStripeCustomer(
            organization_id=organization_id,
            stripe_customer_id=stripe_customer_id,
        )

        self.db.add(organization_stripe_customer)

        return organization_stripe_customer

    def get_teams_by_organization(self, organization_id):
        """
        Return a list of all team objects for the specified organization,
        or None if there are none.
        """
        return (
            self.db.execute(select(Team).where(Team.organization_id == organization_id))
            .scalars()
            .all()
        )

    def get_team(self, team_id):
        """
        Return a team object for the specified identifier,
        """
        return self.db.get(Team, team_id)

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

        return team

    def rename_team(self, team_id, name):
        """
        Performs operations necessary to rename a Team
        """
        team = self.get_team(team_id)

        team.name = name

        return team

    def delete_team(self, team_id):
        """
        Delete team for the specified team id and all associated objects
        """
        team = self.get_team(team_id)
        # Delete team members
        self.db.execute(delete(TeamRole).filter_by(team=team))
        # Delete projects
        self.db.execute(delete(TeamProjectRole).filter_by(team=team))
        # Delete team
        self.db.execute(delete(Team).where(Team.id == team_id))

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
        return self.db.get(TeamRole, team_role_id)

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

        return member

    def delete_team_role(self, team_role_id):
        """
        Remove the team role for a specified team id and user id
        """
        member = self.get_team_role(team_role_id)

        self.db.delete(member)

    def get_team_project_role(self, team_project_role_id):
        """
        Return the team project role object that
        represents the given team project role id,
        """
        return self.db.get(TeamProjectRole, team_project_role_id)

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

        return team_project_role

    def delete_team_project_role(self, team_project_role_id):
        """
        Remove a team project role for a specified team project role id
        """
        team_project_role = self.get_team_project_role(team_project_role_id)

        self.db.delete(team_project_role)


def database_organization_factory(context, request):
    return DatabaseOrganizationService(request.db)
