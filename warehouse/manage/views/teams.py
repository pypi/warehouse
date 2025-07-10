# SPDX-License-Identifier: Apache-2.0

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPSeeOther
from pyramid.view import view_config, view_defaults
from sqlalchemy.exc import NoResultFound
from webob.multidict import MultiDict

from warehouse.accounts import IUserService
from warehouse.authnz import Permissions
from warehouse.email import (
    send_added_as_team_member_email,
    send_removed_as_team_collaborator_email,
    send_removed_as_team_member_email,
    send_role_changed_as_team_collaborator_email,
    send_team_collaborator_removed_email,
    send_team_collaborator_role_changed_email,
    send_team_deleted_email,
    send_team_member_added_email,
    send_team_member_removed_email,
)
from warehouse.events.tags import EventTag
from warehouse.manage.forms import (
    ChangeTeamProjectRoleForm,
    CreateTeamRoleForm,
    SaveTeamForm,
)
from warehouse.manage.views import (
    organization_managers,
    organization_members,
    organization_owners,
    user_projects,
)
from warehouse.organizations import IOrganizationService
from warehouse.organizations.models import (
    Team,
    TeamProjectRole,
    TeamProjectRoleType,
    TeamRoleType,
)
from warehouse.packaging import Project
from warehouse.packaging.models import JournalEntry
from warehouse.utils.organization import confirm_team
from warehouse.utils.paginate import paginate_url_factory


@view_defaults(
    route_name="manage.team.settings",
    context=Team,
    renderer="manage/team/settings.html",
    uses_session=True,
    require_active_organization=True,
    require_csrf=True,
    require_methods=False,
    permission=Permissions.OrganizationTeamsManage,
    has_translations=True,
    require_reauth=True,
)
class ManageTeamSettingsViews:
    def __init__(self, team, request):
        self.team = team
        self.request = request
        self.user_service = request.find_service(IUserService, context=None)
        self.organization_service = request.find_service(
            IOrganizationService, context=None
        )

    @property
    def default_response(self):
        return {
            "team": self.team,
            "save_team_form": SaveTeamForm(
                formdata=MultiDict(
                    {
                        "name": self.team.name,
                    }
                ),
                organization_service=self.organization_service,
                organization_id=self.team.organization_id,
                team_id=self.team.id,
            ),
        }

    @view_config(request_method="GET", permission=Permissions.OrganizationTeamsRead)
    def manage_team(self):
        return self.default_response

    @view_config(request_method="POST", request_param=SaveTeamForm.__params__)
    def save_team(self):
        form = SaveTeamForm(
            self.request.POST,
            organization_service=self.organization_service,
            organization_id=self.team.organization_id,
            team_id=self.team.id,
        )

        if form.validate():
            name = form.name.data
            previous_team_name = self.team.name
            self.organization_service.rename_team(self.team.id, name)
            self.team.organization.record_event(
                tag=EventTag.Organization.TeamRename,
                request=self.request,
                additional={
                    "team_name": self.team.name,
                    "previous_team_name": previous_team_name,
                    "renamed_by_user_id": str(self.request.user.id),
                },
            )
            self.team.record_event(
                tag=EventTag.Team.TeamRename,
                request=self.request,
                additional={
                    "previous_team_name": previous_team_name,
                    "renamed_by_user_id": str(self.request.user.id),
                },
            )
            self.request.session.flash("Team name updated", queue="success")
            return HTTPSeeOther(
                self.request.route_path(
                    "manage.team.settings",
                    organization_name=self.team.organization.normalized_name,
                    team_name=self.team.normalized_name,
                )
            )

        return {**self.default_response, "save_team_form": form}

    @view_config(request_method="POST", request_param=["confirm_team_name"])
    def delete_team(self):
        # Confirm team name.
        confirm_team(self.team, self.request, fail_route="manage.team.settings")

        # Get organization and team name before deleting team.
        organization = self.team.organization
        team_name = self.team.name

        # Record events.
        organization.record_event(
            tag=EventTag.Organization.TeamDelete,
            request=self.request,
            additional={
                "deleted_by_user_id": str(self.request.user.id),
                "team_name": team_name,
            },
        )
        self.team.record_event(
            tag=EventTag.Team.TeamDelete,
            request=self.request,
            additional={
                "deleted_by_user_id": str(self.request.user.id),
            },
        )

        # Delete team.
        self.organization_service.delete_team(self.team.id)

        # Send notification emails.
        owner_and_manager_users = set(
            organization_owners(self.request, organization)
            + organization_managers(self.request, organization)
        )
        send_team_deleted_email(
            self.request,
            owner_and_manager_users,
            organization_name=organization.name,
            team_name=team_name,
        )

        # Display notification message.
        self.request.session.flash("Team deleted", queue="success")

        return HTTPSeeOther(
            self.request.route_path(
                "manage.organization.teams",
                organization_name=organization.normalized_name,
            )
        )


@view_defaults(
    route_name="manage.team.projects",
    context=Team,
    renderer="manage/team/projects.html",
    uses_session=True,
    require_active_organization=True,
    require_csrf=True,
    require_methods=False,
    permission=Permissions.OrganizationTeamsManage,
    has_translations=True,
    require_reauth=True,
)
class ManageTeamProjectsViews:
    def __init__(self, team, request):
        self.team = team
        self.request = request

    @property
    def active_projects(self):
        return self.team.projects

    @property
    def default_response(self):
        active_projects = self.active_projects
        all_user_projects = user_projects(self.request)
        projects_owned = {
            project.name for project in all_user_projects["projects_owned"]
        }
        projects_sole_owned = {
            project.name for project in all_user_projects["projects_sole_owned"]
        }

        return {
            "team": self.team,
            "active_projects": active_projects,
            "projects_owned": projects_owned,
            "projects_sole_owned": projects_sole_owned,
        }

    @view_config(request_method="GET", permission=Permissions.OrganizationTeamsRead)
    def manage_team_projects(self):
        return self.default_response


@view_defaults(
    route_name="manage.team.roles",
    context=Team,
    renderer="manage/team/roles.html",
    uses_session=True,
    require_active_organization=True,
    require_csrf=True,
    require_methods=False,
    permission=Permissions.OrganizationTeamsManage,
    has_translations=True,
    require_reauth=True,
)
class ManageTeamRolesViews:
    def __init__(self, team, request):
        self.team = team
        self.request = request
        self.organization_service = request.find_service(
            IOrganizationService, context=None
        )
        self.user_service = request.find_service(IUserService, context=None)
        self.user_choices = sorted(
            user.username
            for user in set(
                organization_owners(self.request, self.team.organization)
                + organization_managers(self.request, self.team.organization)
                + organization_members(self.request, self.team.organization)
            )
            if user not in self.team.members
        )

    @property
    def default_response(self):
        return {
            "team": self.team,
            "roles": self.organization_service.get_team_roles(self.team.id),
            "form": CreateTeamRoleForm(
                self.request.POST,
                user_choices=self.user_choices,
            ),
        }

    @view_config(request_method="GET", permission=Permissions.OrganizationTeamsRead)
    def manage_team_roles(self):
        return self.default_response

    @view_config(request_method="POST")
    def create_team_role(self):
        # Get and validate form from default response.
        default_response = self.default_response
        form = default_response["form"]
        if not form.validate():
            return default_response

        # Add user to team.
        username = form.username.data
        role_name = TeamRoleType.Member
        user_id = self.user_service.find_userid(username)
        role = self.organization_service.add_team_role(
            team_id=self.team.id,
            user_id=user_id,
            role_name=role_name,
        )

        # Record events.
        self.team.organization.record_event(
            tag=EventTag.Organization.TeamRoleAdd,
            request=self.request,
            additional={
                "submitted_by_user_id": str(self.request.user.id),
                "team_name": self.team.name,
                "role_name": role_name.value,
                "target_user_id": str(user_id),
            },
        )
        self.team.record_event(
            tag=EventTag.Team.TeamRoleAdd,
            request=self.request,
            additional={
                "submitted_by_user_id": str(self.request.user.id),
                "role_name": role_name.value,
                "target_user_id": str(user_id),
            },
        )
        role.user.record_event(
            tag=EventTag.Account.TeamRoleAdd,
            request=self.request,
            additional={
                "submitted_by_user_id": str(self.request.user.id),
                "organization_name": self.team.organization.name,
                "team_name": self.team.name,
                "role_name": role_name.value,
            },
        )

        # Send notification emails.
        owner_and_manager_users = set(
            organization_owners(self.request, self.team.organization)
            + organization_managers(self.request, self.team.organization)
        )
        owner_and_manager_users.discard(role.user)
        send_team_member_added_email(
            self.request,
            owner_and_manager_users,
            user=role.user,
            submitter=self.request.user,
            organization_name=self.team.organization.name,
            team_name=self.team.name,
        )
        send_added_as_team_member_email(
            self.request,
            role.user,
            submitter=self.request.user,
            organization_name=self.team.organization.name,
            team_name=self.team.name,
        )

        # Display notification message.
        self.request.session.flash(
            f"Added the team {self.team.name!r} to {self.team.organization.name!r}",
            queue="success",
        )

        # Refresh teams list.
        return HTTPSeeOther(self.request.path)

    @view_config(
        request_method="POST",
        route_name="manage.team.delete_role",
        permission=Permissions.OrganizationTeamsRead,
    )
    def delete_team_role(self):
        # Get team role.
        role_id = self.request.POST["role_id"]
        role = self.organization_service.get_team_role(role_id)

        if not role or role.team_id != self.team.id:
            self.request.session.flash("Could not find member", queue="error")
        elif (
            not self.request.has_permission(Permissions.OrganizationTeamsManage)
            and role.user != self.request.user
        ):
            self.request.session.flash(
                "Cannot remove other people from the team", queue="error"
            )
        else:
            # Delete team role.
            self.organization_service.delete_team_role(role.id)

            # Record events.
            self.team.organization.record_event(
                tag=EventTag.Organization.TeamRoleRemove,
                request=self.request,
                additional={
                    "submitted_by_user_id": str(self.request.user.id),
                    "team_name": self.team.name,
                    "role_name": role.role_name.value,
                    "target_user_id": str(role.user.id),
                },
            )
            self.team.record_event(
                tag=EventTag.Team.TeamRoleRemove,
                request=self.request,
                additional={
                    "submitted_by_user_id": str(self.request.user.id),
                    "role_name": role.role_name.value,
                    "target_user_id": str(role.user.id),
                },
            )
            role.user.record_event(
                tag=EventTag.Account.TeamRoleRemove,
                request=self.request,
                additional={
                    "submitted_by_user_id": str(self.request.user.id),
                    "organization_name": self.team.organization.name,
                    "team_name": self.team.name,
                    "role_name": role.role_name.value,
                },
            )

            # Send notification emails.
            owner_and_manager_users = set(
                organization_owners(self.request, self.team.organization)
                + organization_managers(self.request, self.team.organization)
            )
            owner_and_manager_users.discard(role.user)
            send_team_member_removed_email(
                self.request,
                owner_and_manager_users,
                user=role.user,
                submitter=self.request.user,
                organization_name=self.team.organization.name,
                team_name=self.team.name,
            )
            send_removed_as_team_member_email(
                self.request,
                role.user,
                submitter=self.request.user,
                organization_name=self.team.organization.name,
                team_name=self.team.name,
            )

            # Display notification message.
            self.request.session.flash("Removed from team", queue="success")

        # Refresh teams list.
        return HTTPSeeOther(
            self.request.route_path(
                "manage.team.roles",
                organization_name=self.team.organization.normalized_name,
                team_name=self.team.normalized_name,
            )
        )


@view_config(
    route_name="manage.team.history",
    context=Team,
    renderer="manage/team/history.html",
    uses_session=True,
    permission=Permissions.OrganizationTeamsManage,
    has_translations=True,
)
def manage_team_history(team, request):
    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.")

    events_query = (
        request.db.query(Team.Event)
        .join(Team.Event.source)
        .filter(Team.Event.source_id == team.id)
        .order_by(Team.Event.time.desc())
        .order_by(Team.Event.tag.desc())
    )

    events = SQLAlchemyORMPage(
        events_query,
        page=page_num,
        items_per_page=25,
        url_maker=paginate_url_factory(request),
    )

    if events.page_count and page_num > events.page_count:
        raise HTTPNotFound

    user_service = request.find_service(IUserService, context=None)

    return {
        "events": events,
        "get_user": user_service.get_user,
        "team": team,
    }


@view_config(
    route_name="manage.project.change_team_project_role",
    context=Project,
    uses_session=True,
    require_methods=["POST"],
    permission=Permissions.ProjectsWrite,
    has_translations=True,
    require_reauth=True,
)
def change_team_project_role(project, request, _form_class=ChangeTeamProjectRoleForm):
    form = _form_class(request.POST)

    if form.validate():
        role_id = request.POST["role_id"]
        try:
            role = (
                request.db.query(TeamProjectRole)
                .join(Team)
                .filter(
                    TeamProjectRole.id == role_id, TeamProjectRole.project == project
                )
                .one()
            )
            if (
                role.role_name == TeamProjectRoleType.Owner
                and request.user in role.team.members
                and request.user not in role.team.organization.owners
            ):
                request.session.flash(
                    "Cannot remove your own team as Owner",
                    queue="error",
                )
            else:
                # Add journal entry.
                request.db.add(
                    JournalEntry(
                        name=project.name,
                        action="change {} {} to {}".format(
                            role.role_name.value,
                            role.team.name,
                            form.team_project_role_name.data.value,
                        ),
                        submitted_by=request.user,
                    )
                )

                # Change team project role.
                role.role_name = form.team_project_role_name.data

                # Record events.
                project.record_event(
                    tag=EventTag.Project.TeamProjectRoleChange,
                    request=request,
                    additional={
                        "submitted_by_user_id": str(request.user.id),
                        "role_name": role.role_name.value,
                        "target_team": role.team.name,
                    },
                )
                role.team.organization.record_event(
                    tag=EventTag.Organization.TeamProjectRoleChange,
                    request=request,
                    additional={
                        "submitted_by_user_id": str(request.user.id),
                        "project_name": role.project.name,
                        "role_name": role.role_name.value,
                        "target_team": role.team.name,
                    },
                )
                role.team.record_event(
                    tag=EventTag.Team.TeamProjectRoleChange,
                    request=request,
                    additional={
                        "submitted_by_user_id": str(request.user.id),
                        "project_name": role.project.name,
                        "role_name": role.role_name.value,
                    },
                )

                # Send notification emails.
                member_users = set(role.team.members)
                owner_users = set(project.owners + role.team.organization.owners)
                owner_users -= member_users
                send_team_collaborator_role_changed_email(
                    request,
                    owner_users,
                    team=role.team,
                    submitter=request.user,
                    project_name=project.name,
                    role=role.role_name.value,
                )
                send_role_changed_as_team_collaborator_email(
                    request,
                    member_users,
                    team=role.team,
                    submitter=request.user,
                    project_name=project.name,
                    role=role.role_name.value,
                )

                # Display notification message.
                request.session.flash("Changed permissions", queue="success")
        except NoResultFound:
            request.session.flash("Could not find permissions", queue="error")

    return HTTPSeeOther(
        request.route_path("manage.project.roles", project_name=project.name)
    )


@view_config(
    route_name="manage.project.delete_team_project_role",
    context=Project,
    uses_session=True,
    require_methods=["POST"],
    permission=Permissions.ProjectsWrite,
    has_translations=True,
    require_reauth=True,
)
def delete_team_project_role(project, request):
    try:
        role = (
            request.db.query(TeamProjectRole)
            .join(Team)
            .filter(TeamProjectRole.project == project)
            .filter(TeamProjectRole.id == request.POST["role_id"])
            .one()
        )
        removing_self = (
            role.role_name == TeamProjectRoleType.Owner
            and request.user in role.team.members
            and request.user not in role.team.organization.owners
        )
        if removing_self:
            request.session.flash("Cannot remove your own team as Owner", queue="error")
        else:
            role_name = role.role_name
            team = role.team

            # Delete role.
            request.db.delete(role)

            # Add journal entry.
            request.db.add(
                JournalEntry(
                    name=project.name,
                    action=f"remove {role_name.value} {team.name}",
                    submitted_by=request.user,
                )
            )

            # Record event.
            project.record_event(
                tag=EventTag.Project.TeamProjectRoleRemove,
                request=request,
                additional={
                    "submitted_by_user_id": str(request.user.id),
                    "role_name": role_name.value,
                    "target_team": team.name,
                },
            )
            team.organization.record_event(
                tag=EventTag.Organization.TeamProjectRoleRemove,
                request=request,
                additional={
                    "submitted_by_user_id": str(request.user.id),
                    "project_name": project.name,
                    "role_name": role_name.value,
                    "target_team": team.name,
                },
            )
            team.record_event(
                tag=EventTag.Team.TeamProjectRoleRemove,
                request=request,
                additional={
                    "submitted_by_user_id": str(request.user.id),
                    "project_name": project.name,
                    "role_name": role_name.value,
                },
            )

            # Send notification emails.
            member_users = set(team.members)
            owner_users = set(project.owners + team.organization.owners)
            owner_users -= member_users
            send_team_collaborator_removed_email(
                request,
                owner_users,
                team=role.team,
                submitter=request.user,
                project_name=project.name,
            )
            send_removed_as_team_collaborator_email(
                request,
                member_users,
                team=role.team,
                submitter=request.user,
                project_name=project.name,
            )

            # Display notification message.
            request.session.flash("Removed permissions", queue="success")
    except NoResultFound:
        request.session.flash("Could not find permissions", queue="error")

    return HTTPSeeOther(
        request.route_path("manage.project.roles", project_name=project.name)
    )
