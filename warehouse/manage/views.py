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

from collections import defaultdict

from pyramid.httpexceptions import HTTPSeeOther
from pyramid.security import Authenticated
from pyramid.view import view_config
from sqlalchemy.orm.exc import NoResultFound

from warehouse.accounts.interfaces import IUserService
from warehouse.accounts.models import User
from warehouse.manage.forms import CreateRoleForm, ChangeRoleForm
from warehouse.packaging.models import JournalEntry, Role


@view_config(
    route_name="manage.profile",
    renderer="manage/profile.html",
    uses_session=True,
    effective_principals=Authenticated,
)
def manage_profile(request):
    return {}


@view_config(
    route_name="manage.projects",
    renderer="manage/projects.html",
    uses_session=True,
    effective_principals=Authenticated,
)
def manage_projects(request):
    return {}


@view_config(
    route_name="manage.project.settings",
    renderer="manage/project.html",
    uses_session=True,
    permission="manage",
    effective_principals=Authenticated,
)
def manage_project_settings(project, request):
    return {"project": project}


@view_config(
    route_name="manage.project.roles",
    renderer="manage/roles.html",
    uses_session=True,
    require_methods=False,
    permission="manage",
)
def manage_project_roles(project, request, _form_class=CreateRoleForm):
    user_service = request.find_service(IUserService, context=None)
    form = _form_class(request.POST, user_service=user_service)

    if request.method == "POST" and form.validate():
        username = form.username.data
        role_name = form.role_name.data
        userid = user_service.find_userid(username)
        user = user_service.get_user(userid)

        if (request.db.query(
                request.db.query(Role).filter(
                    Role.user == user,
                    Role.project == project,
                    Role.role_name == role_name,
                )
                .exists()).scalar()):
            request.session.flash(
                f"User '{username}' already has {role_name} role for project",
                queue="error"
            )
        else:
            request.db.add(
                Role(user=user, project=project, role_name=form.role_name.data)
            )
            request.db.add(
                JournalEntry(
                    name=project.name,
                    action=f"add {role_name} {username}",
                    submitted_by=request.user,
                    submitted_from=request.remote_addr,
                ),
            )
            request.session.flash(
                f"Added collaborator '{form.username.data}'",
                queue="success"
            )
        form = _form_class(user_service=user_service)

    roles = (
        request.db.query(Role)
        .join(User)
        .filter(Role.project == project)
        .all()
    )

    # TODO: The following lines are a hack to handle multiple roles for a
    # single user and should be removed when fixing GH-2745
    roles_by_user = defaultdict(list)
    for role in roles:
        roles_by_user[role.user.username].append(role)

    return {
        "project": project,
        "roles_by_user": roles_by_user,
        "form": form,
    }


@view_config(
    route_name="manage.project.change_role",
    uses_session=True,
    require_methods=["POST"],
    permission="manage",
)
def change_project_role(project, request, _form_class=ChangeRoleForm):
    # TODO: This view was modified to handle deleting multiple roles for a
    # single user and should be updated when fixing GH-2745

    form = _form_class(request.POST)

    if form.validate():
        role_ids = request.POST.getall('role_id')

        if len(role_ids) > 1:
            # This user has more than one role, so just delete all the ones
            # that aren't what we want.
            #
            # TODO: This branch should be removed when fixing GH-2745.
            roles = (
                request.db.query(Role)
                .filter(
                    Role.id.in_(role_ids),
                    Role.project == project,
                    Role.role_name != form.role_name.data
                )
                .all()
            )
            removing_self = any(
                role.role_name == "Owner" and role.user == request.user
                for role in roles
            )
            if removing_self:
                request.session.flash(
                    "Cannot remove yourself as Owner", queue="error"
                )
            else:
                for role in roles:
                    request.db.delete(role)
                    request.db.add(
                        JournalEntry(
                            name=project.name,
                            action=f"remove {role.role_name} {role.user_name}",
                            submitted_by=request.user,
                            submitted_from=request.remote_addr,
                        ),
                    )
                request.session.flash(
                    'Successfully changed role', queue="success"
                )
        else:
            # This user only has one role, so get it and change the type.
            try:
                role = (
                    request.db.query(Role)
                    .filter(
                        Role.id == request.POST.get('role_id'),
                        Role.project == project,
                    )
                    .one()
                )
                if role.role_name == "Owner" and role.user == request.user:
                    request.session.flash(
                        "Cannot remove yourself as Owner", queue="error"
                    )
                else:
                    request.db.add(
                        JournalEntry(
                            name=project.name,
                            action="change {} {} to {}".format(
                                role.role_name,
                                role.user_name,
                                form.role_name.data,
                            ),
                            submitted_by=request.user,
                            submitted_from=request.remote_addr,
                        ),
                    )
                    role.role_name = form.role_name.data
                    request.session.flash(
                        'Successfully changed role', queue="success"
                    )
            except NoResultFound:
                request.session.flash("Could not find role", queue="error")

    return HTTPSeeOther(
        request.route_path('manage.project.roles', name=project.name)
    )


@view_config(
    route_name="manage.project.delete_role",
    uses_session=True,
    require_methods=["POST"],
    permission="manage",
)
def delete_project_role(project, request):
    # TODO: This view was modified to handle deleting multiple roles for a
    # single user and should be updated when fixing GH-2745

    roles = (
        request.db.query(Role)
        .filter(
            Role.id.in_(request.POST.getall('role_id')),
            Role.project == project,
        )
        .all()
    )
    removing_self = any(
        role.role_name == "Owner" and role.user == request.user
        for role in roles
    )

    if not roles:
        request.session.flash("Could not find role", queue="error")
    elif removing_self:
        request.session.flash("Cannot remove yourself as Owner", queue="error")
    else:
        for role in roles:
            request.db.delete(role)
            request.db.add(
                JournalEntry(
                    name=project.name,
                    action=f"remove {role.role_name} {role.user_name}",
                    submitted_by=request.user,
                    submitted_from=request.remote_addr,
                ),
            )
        request.session.flash("Successfully removed role", queue="success")

    return HTTPSeeOther(
        request.route_path('manage.project.roles', name=project.name)
    )
