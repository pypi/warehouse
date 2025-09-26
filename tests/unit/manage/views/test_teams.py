# SPDX-License-Identifier: Apache-2.0

import datetime
import uuid

import pretend
import pytest

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPSeeOther
from sqlalchemy.orm import joinedload
from webob.multidict import MultiDict

from tests.common.db.accounts import UserFactory
from tests.common.db.organizations import (
    OrganizationFactory,
    OrganizationProjectFactory,
    OrganizationRoleFactory,
    TeamEventFactory,
    TeamFactory,
    TeamProjectRoleFactory,
    TeamRoleFactory,
)
from tests.common.db.packaging import ProjectFactory
from warehouse.manage import views
from warehouse.manage.views import teams as team_views
from warehouse.organizations.models import (
    OrganizationRoleType,
    Team,
    TeamProjectRole,
    TeamProjectRoleType,
    TeamRoleType,
)
from warehouse.packaging.models import JournalEntry
from warehouse.utils.paginate import paginate_url_factory


class TestManageTeamSettings:
    def test_manage_team(self, db_request, organization_service, user_service):
        team = TeamFactory.create()

        view = team_views.ManageTeamSettingsViews(team, db_request)
        result = view.manage_team()
        form = result["save_team_form"]

        assert view.request == db_request
        assert view.organization_service == organization_service
        assert view.user_service == user_service
        assert result == {
            "team": team,
            "save_team_form": form,
        }

    def test_save_team(self, db_request, pyramid_user, organization_service):
        team = TeamFactory.create(name="Team Name")
        db_request.POST = MultiDict({"name": "Team name"})
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foo/bar/")

        view = team_views.ManageTeamSettingsViews(team, db_request)
        result = view.save_team()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foo/bar/"
        assert team.name == "Team name"

    def test_save_team_validation_fails(self, db_request, organization_service):
        organization = OrganizationFactory.create()
        team = TeamFactory.create(
            name="Team Name",
            organization=organization,
        )
        TeamFactory.create(
            name="Existing Team Name",
            organization=organization,
        )

        db_request.POST = MultiDict({"name": "Existing Team Name"})

        view = team_views.ManageTeamSettingsViews(team, db_request)
        result = view.save_team()
        form = result["save_team_form"]

        assert result == {
            "team": team,
            "save_team_form": form,
        }
        assert team.name == "Team Name"
        assert form.name.errors == [
            "This team name has already been used. Choose a different team name."
        ]

    def test_delete_team(
        self,
        db_request,
        pyramid_user,
        organization_service,
        user_service,
        monkeypatch,
    ):
        team = TeamFactory.create()
        db_request.POST = MultiDict({"confirm_team_name": team.name})
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foo/bar/")

        send_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(team_views, "send_team_deleted_email", send_email)

        view = team_views.ManageTeamSettingsViews(team, db_request)
        result = view.delete_team()

        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/foo/bar/"
        assert send_email.calls == [
            pretend.call(
                db_request,
                set(),
                organization_name=team.organization.name,
                team_name=team.name,
            ),
        ]

    def test_delete_team_no_confirm(
        self,
        db_request,
        pyramid_user,
        organization_service,
        user_service,
        monkeypatch,
    ):
        team = TeamFactory.create()
        db_request.POST = MultiDict()
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foo/bar/")

        view = team_views.ManageTeamSettingsViews(team, db_request)
        with pytest.raises(HTTPSeeOther):
            view.delete_team()

        assert db_request.session.flash.calls == [
            pretend.call("Confirm the request", queue="error")
        ]

    def test_delete_team_wrong_confirm(
        self,
        db_request,
        pyramid_user,
        organization_service,
        user_service,
        monkeypatch,
    ):
        team = TeamFactory.create(name="Team Name")
        db_request.POST = MultiDict({"confirm_team_name": "TEAM NAME"})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foo/bar/")

        view = team_views.ManageTeamSettingsViews(team, db_request)
        with pytest.raises(HTTPSeeOther):
            view.delete_team()

        assert db_request.session.flash.calls == [
            pretend.call(
                (
                    "Could not delete team - "
                    "'TEAM NAME' is not the same as 'Team Name'"
                ),
                queue="error",
            )
        ]


class TestManageTeamProjects:
    def test_manage_team_projects(
        self,
        db_request,
        pyramid_user,
        organization_service,
        monkeypatch,
    ):
        team = TeamFactory.create()
        project = ProjectFactory.create()

        TeamProjectRoleFactory.create(
            project=project, team=team, role_name=TeamProjectRoleType.Owner
        )

        view = team_views.ManageTeamProjectsViews(team, db_request)
        result = view.manage_team_projects()

        assert view.team == team
        assert view.request == db_request
        assert result == {
            "team": team,
            "active_projects": view.active_projects,
            "projects_owned": set(),
            "projects_sole_owned": set(),
        }


class TestManageTeamRoles:
    def test_manage_team_roles(
        self,
        db_request,
        organization_service,
        user_service,
    ):
        team = TeamFactory.create()

        db_request.POST = MultiDict()

        view = team_views.ManageTeamRolesViews(team, db_request)
        result = view.manage_team_roles()
        form = result["form"]

        assert result == {
            "team": team,
            "roles": [],
            "form": form,
        }

    def test_create_team_role(
        self,
        db_request,
        organization_service,
        user_service,
        monkeypatch,
    ):
        organization = OrganizationFactory.create()
        team = TeamFactory(organization=organization)
        owner = UserFactory.create(username="owner")
        manager = UserFactory.create(username="manager")
        member = UserFactory.create(username="user")
        OrganizationRoleFactory.create(
            organization=organization,
            user=owner,
            role_name=OrganizationRoleType.Owner,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=manager,
            role_name=OrganizationRoleType.Manager,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=member,
            role_name=OrganizationRoleType.Member,
        )

        db_request.method = "POST"
        db_request.POST = MultiDict({"username": member.username})
        db_request.user = owner
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        send_team_member_added_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            team_views,
            "send_team_member_added_email",
            send_team_member_added_email,
        )
        send_added_as_team_member_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            team_views,
            "send_added_as_team_member_email",
            send_added_as_team_member_email,
        )

        view = team_views.ManageTeamRolesViews(team, db_request)
        result = view.create_team_role()
        roles = organization_service.get_team_roles(team.id)

        assert len(roles) == 1
        assert roles[0].team_id == team.id
        assert roles[0].user_id == member.id
        assert send_team_member_added_email.calls == [
            pretend.call(
                db_request,
                {owner, manager},
                user=member,
                submitter=db_request.user,
                organization_name=team.organization.name,
                team_name=team.name,
            )
        ]
        assert send_added_as_team_member_email.calls == [
            pretend.call(
                db_request,
                member,
                submitter=db_request.user,
                organization_name=team.organization.name,
                team_name=team.name,
            )
        ]
        assert db_request.session.flash.calls == [
            pretend.call(
                f"Added the team {team.name!r} to {team.organization.name!r}",
                queue="success",
            )
        ]
        assert isinstance(result, HTTPSeeOther)

    def test_create_team_role_duplicate_member(
        self,
        db_request,
        organization_service,
        user_service,
    ):
        organization = OrganizationFactory.create()
        team = TeamFactory(organization=organization)
        owner = UserFactory.create(username="owner")
        manager = UserFactory.create(username="manager")
        member = UserFactory.create(username="user")
        OrganizationRoleFactory.create(
            organization=organization,
            user=owner,
            role_name=OrganizationRoleType.Owner,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=manager,
            role_name=OrganizationRoleType.Manager,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=member,
            role_name=OrganizationRoleType.Member,
        )
        role = TeamRoleFactory.create(
            team=team,
            user=member,
            role_name=TeamRoleType.Member,
        )

        db_request.method = "POST"
        db_request.POST = MultiDict({"username": member.username})
        db_request.user = owner
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        view = team_views.ManageTeamRolesViews(team, db_request)
        result = view.create_team_role()
        form = result["form"]

        assert organization_service.get_team_roles(team.id) == [role]
        assert db_request.session.flash.calls == []
        assert result == {
            "team": team,
            "roles": [role],
            "form": form,
        }

    def test_create_team_role_not_a_member(
        self,
        db_request,
        organization_service,
        user_service,
    ):
        organization = OrganizationFactory.create()
        team = TeamFactory(organization=organization)
        owner = UserFactory.create(username="owner")
        manager = UserFactory.create(username="manager")
        not_a_member = UserFactory.create(username="user")
        OrganizationRoleFactory.create(
            organization=organization,
            user=owner,
            role_name=OrganizationRoleType.Owner,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=manager,
            role_name=OrganizationRoleType.Manager,
        )

        db_request.method = "POST"
        db_request.POST = MultiDict({"username": not_a_member.username})
        db_request.user = owner
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )

        view = team_views.ManageTeamRolesViews(team, db_request)
        result = view.create_team_role()
        form = result["form"]

        assert result == {
            "team": team,
            "roles": [],
            "form": form,
        }

        assert form.username.errors == ["Not a valid choice."]

    def test_delete_team_role(
        self,
        db_request,
        organization_service,
        user_service,
        monkeypatch,
    ):
        organization = OrganizationFactory.create()
        team = TeamFactory(organization=organization)
        owner = UserFactory.create(username="owner")
        manager = UserFactory.create(username="manager")
        member = UserFactory.create(username="user")
        OrganizationRoleFactory.create(
            organization=organization,
            user=owner,
            role_name=OrganizationRoleType.Owner,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=manager,
            role_name=OrganizationRoleType.Manager,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=member,
            role_name=OrganizationRoleType.Member,
        )
        role = TeamRoleFactory.create(
            team=team,
            user=member,
            role_name=TeamRoleType.Member,
        )

        db_request.method = "POST"
        db_request.POST = MultiDict({"role_id": role.id})
        db_request.user = owner
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foo/bar/")

        send_team_member_removed_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            team_views,
            "send_team_member_removed_email",
            send_team_member_removed_email,
        )
        send_removed_as_team_member_email = pretend.call_recorder(lambda *a, **kw: None)
        monkeypatch.setattr(
            team_views,
            "send_removed_as_team_member_email",
            send_removed_as_team_member_email,
        )

        view = team_views.ManageTeamRolesViews(team, db_request)
        result = view.delete_team_role()

        assert organization_service.get_team_roles(team.id) == []
        assert send_team_member_removed_email.calls == [
            pretend.call(
                db_request,
                {owner, manager},
                user=member,
                submitter=db_request.user,
                organization_name=team.organization.name,
                team_name=team.name,
            )
        ]
        assert send_removed_as_team_member_email.calls == [
            pretend.call(
                db_request,
                member,
                submitter=db_request.user,
                organization_name=team.organization.name,
                team_name=team.name,
            )
        ]
        assert db_request.session.flash.calls == [
            pretend.call("Removed from team", queue="success")
        ]
        assert isinstance(result, HTTPSeeOther)

    def test_delete_team_role_not_a_member(
        self,
        db_request,
        organization_service,
        user_service,
    ):
        organization = OrganizationFactory.create()
        team = TeamFactory(organization=organization)
        other_team = TeamFactory(organization=organization)
        owner = UserFactory.create(username="owner")
        manager = UserFactory.create(username="manager")
        not_a_member = UserFactory.create(username="user")
        OrganizationRoleFactory.create(
            organization=organization,
            user=owner,
            role_name=OrganizationRoleType.Owner,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=manager,
            role_name=OrganizationRoleType.Manager,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=not_a_member,
            role_name=OrganizationRoleType.Member,
        )
        other_team_role = TeamRoleFactory.create(
            team=other_team,
            user=not_a_member,
            role_name=TeamRoleType.Member,
        )

        db_request.method = "POST"
        db_request.POST = MultiDict({"role_id": other_team_role.id})
        db_request.user = owner
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foo/bar/")

        view = team_views.ManageTeamRolesViews(team, db_request)
        result = view.delete_team_role()

        assert organization_service.get_team_roles(team.id) == []
        assert db_request.session.flash.calls == [
            pretend.call("Could not find member", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)

    def test_delete_team_role_not_a_manager(
        self,
        db_request,
        organization_service,
    ):
        organization = OrganizationFactory.create()
        team = TeamFactory(organization=organization)
        owner = UserFactory.create(username="owner")
        not_a_manager = UserFactory.create(username="manager")
        member = UserFactory.create(username="user")
        OrganizationRoleFactory.create(
            organization=organization,
            user=owner,
            role_name=OrganizationRoleType.Owner,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=not_a_manager,
            role_name=OrganizationRoleType.Member,
        )
        OrganizationRoleFactory.create(
            organization=organization,
            user=member,
            role_name=OrganizationRoleType.Member,
        )
        role = TeamRoleFactory.create(
            team=team,
            user=member,
            role_name=TeamRoleType.Member,
        )

        db_request.method = "POST"
        db_request.POST = MultiDict({"role_id": role.id})
        db_request.user = not_a_manager
        db_request.has_permission = lambda *a, **kw: False
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/foo/bar/")

        view = team_views.ManageTeamRolesViews(team, db_request)
        result = view.delete_team_role()

        assert organization_service.get_team_roles(team.id) == [role]
        assert db_request.session.flash.calls == [
            pretend.call("Cannot remove other people from the team", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)


class TestManageTeamHistory:
    def test_get(self, db_request, user_service):
        team = TeamFactory.create()
        older_event = TeamEventFactory.create(
            source=team,
            tag="fake:event",
            time=datetime.datetime(2017, 2, 5, 17, 18, 18, 462_634),
        )
        newer_event = TeamEventFactory.create(
            source=team,
            tag="fake:event",
            time=datetime.datetime(2018, 2, 5, 17, 18, 18, 462_634),
        )

        assert team_views.manage_team_history(team, db_request) == {
            "events": [newer_event, older_event],
            "get_user": user_service.get_user,
            "team": team,
        }

    def test_raises_400_with_pagenum_type_str(self, monkeypatch, db_request):
        params = MultiDict({"page": "abc"})
        db_request.params = params

        events_query = pretend.stub()
        db_request.events_query = pretend.stub(
            events_query=lambda *a, **kw: events_query
        )

        page_obj = pretend.stub(page_count=10, item_count=1000)
        page_cls = pretend.call_recorder(lambda *a, **kw: page_obj)
        monkeypatch.setattr(views, "SQLAlchemyORMPage", page_cls)

        url_maker = pretend.stub()
        url_maker_factory = pretend.call_recorder(lambda request: url_maker)
        monkeypatch.setattr(views, "paginate_url_factory", url_maker_factory)

        team = TeamFactory.create()
        with pytest.raises(HTTPBadRequest):
            team_views.manage_team_history(team, db_request)

        assert page_cls.calls == []

    def test_first_page(self, db_request, user_service):
        page_number = 1
        params = MultiDict({"page": page_number})
        db_request.params = params

        team = TeamFactory.create()
        items_per_page = 25
        total_items = items_per_page + 2
        TeamEventFactory.create_batch(total_items, source=team, tag="fake:event")
        events_query = (
            db_request.db.query(Team.Event)
            .join(Team.Event.source)
            .filter(Team.Event.source_id == team.id)
            .order_by(Team.Event.time.desc())
        )

        events_page = SQLAlchemyORMPage(
            events_query,
            page=page_number,
            items_per_page=items_per_page,
            item_count=total_items,
            url_maker=paginate_url_factory(db_request),
        )
        assert team_views.manage_team_history(team, db_request) == {
            "events": events_page,
            "get_user": user_service.get_user,
            "team": team,
        }

    def test_last_page(self, db_request, user_service):
        page_number = 2
        params = MultiDict({"page": page_number})
        db_request.params = params

        team = TeamFactory.create()
        items_per_page = 25
        total_items = items_per_page + 2
        TeamEventFactory.create_batch(total_items, source=team, tag="fake:event")
        events_query = (
            db_request.db.query(Team.Event)
            .join(Team.Event.source)
            .filter(Team.Event.source_id == team.id)
            .order_by(Team.Event.time.desc())
        )

        events_page = SQLAlchemyORMPage(
            events_query,
            page=page_number,
            items_per_page=items_per_page,
            item_count=total_items,
            url_maker=paginate_url_factory(db_request),
        )
        assert team_views.manage_team_history(team, db_request) == {
            "events": events_page,
            "get_user": user_service.get_user,
            "team": team,
        }

    def test_raises_404_with_out_of_range_page(self, db_request):
        page_number = 3
        params = MultiDict({"page": page_number})
        db_request.params = params

        team = TeamFactory.create()
        items_per_page = 25
        total_items = items_per_page + 2
        TeamEventFactory.create_batch(total_items, source=team, tag="fake:event")

        with pytest.raises(HTTPNotFound):
            assert team_views.manage_team_history(team, db_request)


class TestChangeTeamProjectRole:
    @pytest.fixture
    def organization(self, pyramid_user):
        organization = OrganizationFactory.create()
        OrganizationRoleFactory.create(
            organization=organization,
            user=pyramid_user,
            role_name=OrganizationRoleType.Owner,
        )
        return organization

    @pytest.fixture
    def organization_project(self, organization):
        project = ProjectFactory.create(organization=organization)
        OrganizationProjectFactory(organization=organization, project=project)
        return project

    @pytest.fixture
    def organization_member(self, organization):
        member = UserFactory.create()
        OrganizationRoleFactory.create(
            organization=organization,
            user=member,
            role_name=OrganizationRoleType.Member,
        )
        return member

    @pytest.fixture
    def organization_team(self, organization, organization_member):
        team = TeamFactory(organization=organization)
        TeamRoleFactory.create(team=team, user=organization_member)
        return team

    def test_change_role(
        self,
        db_request,
        pyramid_user,
        organization_member,
        organization_team,
        organization_project,
        monkeypatch,
    ):
        role = TeamProjectRoleFactory.create(
            team=organization_team,
            project=organization_project,
            role_name=TeamProjectRoleType.Owner,
        )
        new_role_name = TeamProjectRoleType.Maintainer

        db_request.method = "POST"
        db_request.POST = MultiDict(
            {"role_id": role.id, "team_project_role_name": new_role_name}
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        send_team_collaborator_role_changed_email = pretend.call_recorder(
            lambda *a, **kw: None
        )
        monkeypatch.setattr(
            team_views,
            "send_team_collaborator_role_changed_email",
            send_team_collaborator_role_changed_email,
        )
        send_role_changed_as_team_collaborator_email = pretend.call_recorder(
            lambda *a, **kw: None
        )
        monkeypatch.setattr(
            team_views,
            "send_role_changed_as_team_collaborator_email",
            send_role_changed_as_team_collaborator_email,
        )

        result = team_views.change_team_project_role(organization_project, db_request)

        assert role.role_name == new_role_name
        assert db_request.route_path.calls == [
            pretend.call("manage.project.roles", project_name=organization_project.name)
        ]
        assert send_team_collaborator_role_changed_email.calls == [
            pretend.call(
                db_request,
                {pyramid_user},
                team=organization_team,
                submitter=pyramid_user,
                project_name=organization_project.name,
                role=new_role_name.value,
            )
        ]
        assert send_role_changed_as_team_collaborator_email.calls == [
            pretend.call(
                db_request,
                {organization_member},
                team=organization_team,
                submitter=pyramid_user,
                project_name=organization_project.name,
                role=new_role_name.value,
            )
        ]
        assert db_request.session.flash.calls == [
            pretend.call("Changed permissions", queue="success")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        entry = (
            db_request.db.query(JournalEntry)
            .options(joinedload(JournalEntry.submitted_by))
            .one()
        )

        assert entry.name == organization_project.name
        assert entry.action == f"change Owner {organization_team.name} to Maintainer"
        assert entry.submitted_by == db_request.user

    def test_change_role_invalid_role_name(self, pyramid_request, organization_project):
        pyramid_request.method = "POST"
        pyramid_request.POST = MultiDict(
            {
                "role_id": str(uuid.uuid4()),
                "team_project_role_name": "Invalid Role Name",
            }
        )
        pyramid_request.route_path = pretend.call_recorder(
            lambda *a, **kw: "/the-redirect"
        )

        result = team_views.change_team_project_role(
            organization_project, pyramid_request
        )

        assert pyramid_request.route_path.calls == [
            pretend.call("manage.project.roles", project_name=organization_project.name)
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_change_missing_role(self, db_request, organization_project):
        missing_role_id = str(uuid.uuid4())

        db_request.method = "POST"
        db_request.POST = MultiDict(
            {"role_id": missing_role_id, "team_project_role_name": "Owner"}
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = team_views.change_team_project_role(organization_project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Could not find permissions", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_change_own_owner_role(
        self,
        db_request,
        organization_member,
        organization_team,
        organization_project,
    ):
        role = TeamProjectRoleFactory.create(
            team=organization_team,
            project=organization_project,
            role_name=TeamProjectRoleType.Owner,
        )

        db_request.method = "POST"
        db_request.user = organization_member
        db_request.POST = MultiDict(
            {"role_id": role.id, "team_project_role_name": "Maintainer"}
        )
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = team_views.change_team_project_role(organization_project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Cannot remove your own team as Owner", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"


class TestDeleteTeamProjectRole:
    @pytest.fixture
    def organization(self, pyramid_user):
        organization = OrganizationFactory.create()
        OrganizationRoleFactory.create(
            organization=organization,
            user=pyramid_user,
            role_name=OrganizationRoleType.Owner,
        )
        return organization

    @pytest.fixture
    def organization_project(self, organization):
        project = ProjectFactory.create(organization=organization)
        OrganizationProjectFactory(organization=organization, project=project)
        return project

    @pytest.fixture
    def organization_member(self, organization):
        member = UserFactory.create()
        OrganizationRoleFactory.create(
            organization=organization,
            user=member,
            role_name=OrganizationRoleType.Member,
        )
        return member

    @pytest.fixture
    def organization_team(self, organization, organization_member):
        team = TeamFactory(organization=organization)
        TeamRoleFactory.create(team=team, user=organization_member)
        return team

    def test_delete_role(
        self,
        db_request,
        organization_member,
        organization_team,
        organization_project,
        pyramid_user,
        monkeypatch,
    ):
        role = TeamProjectRoleFactory.create(
            team=organization_team,
            project=organization_project,
            role_name=TeamProjectRoleType.Owner,
        )

        db_request.method = "POST"
        db_request.POST = MultiDict({"role_id": role.id})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        send_team_collaborator_removed_email = pretend.call_recorder(
            lambda *a, **kw: None
        )
        monkeypatch.setattr(
            team_views,
            "send_team_collaborator_removed_email",
            send_team_collaborator_removed_email,
        )
        send_removed_as_team_collaborator_email = pretend.call_recorder(
            lambda *a, **kw: None
        )
        monkeypatch.setattr(
            team_views,
            "send_removed_as_team_collaborator_email",
            send_removed_as_team_collaborator_email,
        )

        result = team_views.delete_team_project_role(organization_project, db_request)

        assert db_request.route_path.calls == [
            pretend.call("manage.project.roles", project_name=organization_project.name)
        ]
        assert db_request.db.query(TeamProjectRole).all() == []
        assert send_team_collaborator_removed_email.calls == [
            pretend.call(
                db_request,
                {pyramid_user},
                team=organization_team,
                submitter=pyramid_user,
                project_name=organization_project.name,
            )
        ]
        assert send_removed_as_team_collaborator_email.calls == [
            pretend.call(
                db_request,
                {organization_member},
                team=organization_team,
                submitter=pyramid_user,
                project_name=organization_project.name,
            )
        ]
        assert db_request.session.flash.calls == [
            pretend.call("Removed permissions", queue="success")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

        entry = (
            db_request.db.query(JournalEntry)
            .options(joinedload(JournalEntry.submitted_by))
            .one()
        )

        assert entry.name == organization_project.name
        assert entry.action == f"remove Owner {organization_team.name}"
        assert entry.submitted_by == db_request.user

    def test_delete_missing_role(self, db_request, organization_project):
        missing_role_id = str(uuid.uuid4())

        db_request.method = "POST"
        db_request.POST = MultiDict({"role_id": missing_role_id})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = team_views.delete_team_project_role(organization_project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Could not find permissions", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"

    def test_delete_own_owner_role(
        self,
        db_request,
        organization_member,
        organization_team,
        organization_project,
    ):
        role = TeamProjectRoleFactory.create(
            team=organization_team,
            project=organization_project,
            role_name=TeamProjectRoleType.Owner,
        )

        db_request.method = "POST"
        db_request.user = organization_member
        db_request.POST = MultiDict({"role_id": role.id})
        db_request.session = pretend.stub(
            flash=pretend.call_recorder(lambda *a, **kw: None)
        )
        db_request.route_path = pretend.call_recorder(lambda *a, **kw: "/the-redirect")

        result = team_views.delete_team_project_role(organization_project, db_request)

        assert db_request.session.flash.calls == [
            pretend.call("Cannot remove your own team as Owner", queue="error")
        ]
        assert isinstance(result, HTTPSeeOther)
        assert result.headers["Location"] == "/the-redirect"
