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

import pretend

from zope.interface.verify import verifyClass

from warehouse.organizations import services
from warehouse.organizations.interfaces import IOrganizationService
from warehouse.organizations.models import (
    OrganizationInvitation,
    OrganizationNameCatalog,
    OrganizationProject,
    OrganizationRole,
    OrganizationRoleType,
    OrganizationType,
    Team,
    TeamProjectRole,
    TeamRole,
)

from ...common.db.organizations import (
    OrganizationFactory,
    OrganizationInvitationFactory,
    OrganizationProjectFactory,
    OrganizationRoleFactory,
    TeamFactory,
    TeamProjectRoleFactory,
    TeamRoleFactory,
    UserFactory,
)
from ...common.db.packaging import ProjectFactory


def test_database_organizations_factory():
    db = pretend.stub()
    remote_addr = pretend.stub()
    context = pretend.stub()
    request = pretend.stub(db=db, remote_addr=remote_addr)

    service = services.database_organization_factory(context, request)
    assert service.db is db
    assert service.remote_addr is remote_addr


class TestDatabaseOrganizationService:
    def test_verify_service(self):
        assert verifyClass(IOrganizationService, services.DatabaseOrganizationService)

    def test_service_creation(self, remote_addr):
        session = pretend.stub()
        service = services.DatabaseOrganizationService(session, remote_addr=remote_addr)

        assert service.db is session
        assert service.remote_addr is remote_addr

    def test_get_organization(self, organization_service):
        organization = OrganizationFactory.create()
        assert organization_service.get_organization(organization.id) == organization

    def test_get_organization_by_name(self, organization_service):
        organization = OrganizationFactory.create()
        assert (
            organization_service.get_organization_by_name(organization.name)
            == organization
        )

    def test_find_organizationid(self, organization_service):
        organization = OrganizationFactory.create()
        assert (
            organization_service.find_organizationid(organization.name)
            == organization.id
        )

    def test_find_organizationid_nonexistent_org(self, organization_service):
        assert organization_service.find_organizationid("a_spoon_in_the_matrix") is None

    def test_get_organizations(self, organization_service):
        organization = OrganizationFactory.create(name="org")
        another_organization = OrganizationFactory.create(name="another_org")
        orgs = organization_service.get_organizations()

        assert organization in orgs
        assert another_organization in orgs

    def test_get_organizations_needing_approval(self, organization_service):
        i_need_it = OrganizationFactory.create()
        assert i_need_it.is_approved is None

        i_has_it = OrganizationFactory.create()
        organization_service.approve_organization(i_has_it.id)
        assert i_has_it.is_approved is True

        orgs_needing_approval = (
            organization_service.get_organizations_needing_approval()
        )

        assert i_need_it in orgs_needing_approval
        assert i_has_it not in orgs_needing_approval

    def test_get_organizations_by_user(self, organization_service, user_service):
        user_organization = OrganizationFactory.create()
        user = UserFactory.create()
        organization_service.add_organization_role(
            user_organization.id,
            user.id,
            OrganizationRoleType.Owner.value,
        )

        another_user_organization = OrganizationFactory.create()
        another_user = UserFactory.create()
        organization_service.add_organization_role(
            another_user_organization.id,
            another_user.id,
            OrganizationRoleType.Owner.value,
        )

        user_orgs = organization_service.get_organizations_by_user(user.id)
        another_user_orgs = organization_service.get_organizations_by_user(
            another_user.id
        )

        assert user_organization in user_orgs
        assert user_organization not in another_user_orgs
        assert another_user_organization in another_user_orgs
        assert another_user_organization not in user_orgs

    def test_add_organization(self, organization_service):
        organization = OrganizationFactory.create()
        new_org = organization_service.add_organization(
            name=organization.name,
            display_name=organization.display_name,
            orgtype=organization.orgtype,
            link_url=organization.link_url,
            description=organization.description,
        )
        organization_service.db.flush()
        org_from_db = organization_service.get_organization(new_org.id)

        assert org_from_db.name == organization.name
        assert org_from_db.display_name == organization.display_name
        assert org_from_db.orgtype == organization.orgtype
        assert org_from_db.link_url == organization.link_url
        assert org_from_db.description == organization.description
        assert not org_from_db.is_active

    def test_get_organization_role(self, organization_service, user_service):
        organization_role = OrganizationRoleFactory.create()

        assert (
            organization_service.get_organization_role(organization_role.id)
            == organization_role
        )

    def test_get_organization_role_by_user(self, organization_service, user_service):
        organization_role = OrganizationRoleFactory.create()

        assert (
            organization_service.get_organization_role_by_user(
                organization_role.organization_id,
                organization_role.user_id,
            )
            == organization_role
        )

    def test_get_organization_role_by_user_nonexistent_role(self, organization_service):
        user = UserFactory.create()
        organization = OrganizationFactory.create()

        assert (
            organization_service.get_organization_role_by_user(organization.id, user.id)
            is None
        )

    def test_get_organization_roles(self, organization_service, user_service):
        organization = OrganizationFactory.create()
        user = UserFactory.create()
        another_user = UserFactory.create()

        added_owner = organization_service.add_organization_role(
            organization.id,
            user.id,
            OrganizationRoleType.Owner.value,
        )
        added_member = organization_service.add_organization_role(
            organization.id,
            another_user.id,
            OrganizationRoleType.Member.value,
        )

        org_roles = organization_service.get_organization_roles(organization.id)

        assert added_owner in org_roles
        assert added_member in org_roles

    def test_add_organization_role(self, organization_service, user_service):
        user = UserFactory.create()
        organization = OrganizationFactory.create()

        added_role = organization_service.add_organization_role(
            organization.id,
            user.id,
            OrganizationRoleType.Owner.value,
        )
        assert added_role.role_name == OrganizationRoleType.Owner.value
        assert added_role.user_id == user.id
        assert added_role.organization_id == organization.id

    def test_delete_organization_role(self, organization_service, user_service):
        organization_role = OrganizationRoleFactory.create()

        organization_service.delete_organization_role(organization_role.id)

        assert (
            organization_service.get_organization_role_by_user(
                organization_role.organization_id,
                organization_role.user_id,
            )
            is None
        )

    def test_get_organization_invite(self, organization_service):
        organization_invite = OrganizationInvitationFactory.create()

        assert (
            organization_service.get_organization_invite(organization_invite.id)
            is not None
        )

    def test_get_organization_invite_by_user(self, organization_service):
        organization_invite = OrganizationInvitationFactory.create()

        assert (
            organization_service.get_organization_invite_by_user(
                organization_invite.organization_id, organization_invite.user_id
            )
            is not None
        )

    def test_get_organization_invite_by_user_nonexistent_invite(
        self, organization_service
    ):
        user = UserFactory.create()
        organization = OrganizationFactory.create()

        assert (
            organization_service.get_organization_invite_by_user(
                organization.id, user.id
            )
            is None
        )

    def test_get_organization_invites(self, organization_service, user_service):
        user = UserFactory.create()
        organization = OrganizationFactory.create()
        another_organization = OrganizationFactory.create()

        invite = organization_service.add_organization_invite(
            organization.id,
            user.id,
            "some_token",
        )
        another_invite = organization_service.add_organization_invite(
            another_organization.id,
            user.id,
            "some_token",
        )

        invites = organization_service.get_organization_invites_by_user(user.id)

        assert invite in invites
        assert another_invite in invites

    def test_add_organization_invite(self, organization_service, user_service):
        user = UserFactory.create()
        organization = OrganizationFactory.create()

        added_invite = organization_service.add_organization_invite(
            organization.id,
            user.id,
            "some_token",
        )

        assert added_invite.user_id == user.id
        assert added_invite.organization_id == organization.id
        assert added_invite.token == "some_token"

    def test_delete_organization_invite(self, organization_service):
        organization_invite = OrganizationInvitationFactory.create()

        organization_service.delete_organization_invite(organization_invite.id)

        assert (
            organization_service.get_organization_invite(organization_invite.id) is None
        )

    def test_approve_organization(self, organization_service):
        organization = OrganizationFactory.create()
        organization_service.approve_organization(organization.id)

        assert organization.is_active is True
        assert organization.is_approved is True
        assert organization.date_approved is not None

    def test_decline_organization(self, organization_service):
        organization = OrganizationFactory.create()
        organization_service.decline_organization(organization.id)

        assert organization.is_approved is False
        assert organization.date_approved is not None

    def test_delete_organization(self, organization_service, db_request):
        organization = OrganizationFactory.create()
        TeamFactory.create(organization=organization)
        TeamFactory.create(organization=organization)

        organization_service.delete_organization(organization.id)

        assert not (
            (
                db_request.db.query(OrganizationInvitation)
                .filter_by(organization=organization)
                .count()
            )
        )
        assert not (
            (
                db_request.db.query(OrganizationNameCatalog)
                .filter(OrganizationNameCatalog.organization_id == organization.id)
                .count()
            )
        )
        assert not (
            (
                db_request.db.query(OrganizationProject)
                .filter_by(organization=organization)
                .count()
            )
        )
        assert not (
            (
                db_request.db.query(OrganizationRole)
                .filter_by(organization=organization)
                .count()
            )
        )
        assert not (
            (db_request.db.query(Team).filter_by(organization=organization).count())
        )
        assert organization_service.get_organization(organization.id) is None

    def test_rename_organization(self, organization_service, db_request):
        organization = OrganizationFactory.create()

        organization_service.rename_organization(organization.id, "some_new_name")
        assert organization.name == "some_new_name"

        db_organization = organization_service.get_organization(organization.id)
        assert db_organization.name == "some_new_name"

        assert (
            db_request.db.query(OrganizationNameCatalog)
            .filter(
                OrganizationNameCatalog.normalized_name == organization.normalized_name
            )
            .count()
        )

    def test_update_organization(self, organization_service, db_request):
        organization = OrganizationFactory.create()

        organization_service.update_organization(
            organization.id,
            name="some_new_name",
            display_name="Some New Name",
            orgtype=OrganizationType.Company.value,
        )
        assert organization.name == "some_new_name"
        assert organization.display_name == "Some New Name"
        assert organization.orgtype == OrganizationType.Company

        db_organization = organization_service.get_organization(organization.id)
        assert db_organization.name == "some_new_name"
        assert db_organization.display_name == "Some New Name"
        assert db_organization.orgtype == OrganizationType.Company

        assert (
            db_request.db.query(OrganizationNameCatalog)
            .filter(
                OrganizationNameCatalog.normalized_name
                == db_organization.normalized_name
            )
            .count()
        )

    def test_get_organization_project(self, organization_service):
        organization = OrganizationFactory.create()
        project = ProjectFactory.create()
        organization_project = OrganizationProjectFactory.create(
            organization=organization, project=project
        )

        assert (
            organization_service.get_organization_project(organization.id, project.id)
            == organization_project
        )

    def test_add_organization_project(self, organization_service, db_request):
        organization = OrganizationFactory.create()
        project = ProjectFactory.create()

        organization_service.add_organization_project(organization.id, project.id)
        assert (
            db_request.db.query(OrganizationProject)
            .filter(
                OrganizationProject.organization_id == organization.id,
                OrganizationProject.project_id == project.id,
            )
            .count()
        )

    def test_delete_organization_project(self, organization_service, db_request):
        organization = OrganizationFactory.create()
        project = ProjectFactory.create()
        OrganizationProjectFactory.create(organization=organization, project=project)

        organization_service.delete_organization_project(organization.id, project.id)
        assert not (
            db_request.db.query(OrganizationProject)
            .filter(
                OrganizationProject.organization_id == organization.id,
                OrganizationProject.project_id == project.id,
            )
            .count()
        )

    def test_get_teams_by_organization(self, organization_service):
        organization = OrganizationFactory.create()

        team = TeamFactory.create(organization=organization)
        teams = organization_service.get_teams_by_organization(organization.id)
        assert len(teams) == 1
        assert team in teams

        team2 = TeamFactory.create(organization=organization)
        teams = organization_service.get_teams_by_organization(organization.id)

        assert len(teams) == 2
        assert team in teams
        assert team2 in teams

    def test_get_team(self, organization_service):
        team = TeamFactory.create()
        assert organization_service.get_team(team.id) == team

    def test_find_teamid(self, organization_service):
        organization = OrganizationFactory.create()
        team = TeamFactory.create(organization=organization)
        assert organization_service.find_teamid(organization.id, team.name) == team.id

    def test_find_teamid_nonexistent_org(self, organization_service):
        organization = OrganizationFactory.create()
        assert (
            organization_service.find_teamid(organization.id, "a_spoon_in_the_matrix")
            is None
        )

    def test_get_teams_by_user(self, organization_service):
        team = TeamFactory.create()
        user = UserFactory.create()
        TeamRoleFactory.create(team=team, user=user)

        teams = organization_service.get_teams_by_user(user.id)
        assert team in teams

        team2 = TeamFactory.create()
        TeamRoleFactory.create(team=team2, user=user)

        teams = organization_service.get_teams_by_user(user.id)
        assert team in teams
        assert team2 in teams

    def test_test_add_team(self, organization_service):
        team = TeamFactory.create()
        new_team = organization_service.add_team(
            name=team.name,
            organization_id=team.organization.id,
        )
        organization_service.db.flush()
        team_from_db = organization_service.get_team(new_team.id)

        assert team_from_db.name == team.name
        assert team_from_db.organization_id == team.organization_id

    def test_rename_team(self, organization_service):
        team = TeamFactory.create()

        organization_service.rename_team(team.id, "some_new_name")
        assert team.name == "some_new_name"

        db_team = organization_service.get_team(team.id)
        assert db_team.name == "some_new_name"

    def test_delete_team(self, organization_service):
        team = TeamFactory.create()
        user = UserFactory.create()
        project = ProjectFactory.create()
        team_role = TeamRoleFactory.create(team=team, user=user)
        team_project_role = TeamProjectRoleFactory.create(team=team, project=project)

        assert organization_service.get_team_role(team_role.id) is not None
        assert (
            organization_service.get_team_project_role(team_project_role.id) is not None
        )

        team_role_id = team_role.id
        team_project_role_id = team_project_role.id

        organization_service.delete_team(team.id)

        assert organization_service.get_team_role(team_role_id) is None
        assert organization_service.get_team_project_role(team_project_role_id) is None
        assert organization_service.get_team(team.id) is None

    def test_delete_teams_by_organization(self, organization_service):
        organization = OrganizationFactory.create()

        team = TeamFactory.create(organization=organization)
        team2 = TeamFactory.create(organization=organization)

        teams = organization_service.get_teams_by_organization(organization.id)
        assert len(teams) == 2
        assert team in teams
        assert team2 in teams

        organization_service.delete_teams_by_organization(organization.id)

        teams = organization_service.get_teams_by_organization(organization.id)
        assert len(teams) == 0
        assert team not in teams
        assert team2 not in teams

    def test_get_team_role(self, organization_service):
        team = TeamFactory.create()
        user = UserFactory.create()
        team_role = TeamRoleFactory.create(team=team, user=user)

        assert organization_service.get_team_role(team_role.id) == team_role

    def test_add_team_role(self, organization_service, db_request):
        team = TeamFactory.create()
        user = UserFactory.create()

        organization_service.add_team_role(team.id, user.id, "Member")
        assert (
            db_request.db.query(TeamRole)
            .filter(
                TeamRole.team_id == team.id,
                TeamRole.user_id == user.id,
                TeamRole.role_name == "Member",
            )
            .count()
        )

    def test_delete_team_role(self, organization_service):
        team = TeamFactory.create()
        user = UserFactory.create()
        team_role = TeamRoleFactory.create(team=team, user=user)
        team_role_id = team_role.id

        organization_service.delete_team_role(team_role.id)
        assert organization_service.get_team_role(team_role_id) is None

    def test_get_team_project_role(self, organization_service):
        team = TeamFactory.create()
        project = ProjectFactory.create()
        team_project_role = TeamProjectRoleFactory.create(team=team, project=project)

        assert (
            organization_service.get_team_project_role(team_project_role.id)
            == team_project_role
        )

    def test_add_team_project_role(self, organization_service, db_request):
        team = TeamFactory.create()
        project = ProjectFactory.create()

        organization_service.add_team_project_role(team.id, project.id, "Owner")
        assert (
            db_request.db.query(TeamProjectRole)
            .filter(
                TeamProjectRole.team_id == team.id,
                TeamProjectRole.project_id == project.id,
                TeamProjectRole.role_name == "Owner",
            )
            .count()
        )

    def test_delete_team_project_role(self, organization_service):
        team = TeamFactory.create()
        project = ProjectFactory.create()
        team_project_role = TeamProjectRoleFactory.create(team=team, project=project)
        team_project_role_id = team_project_role.id

        organization_service.delete_team_project_role(team_project_role.id)
        assert organization_service.get_team_role(team_project_role_id) is None
