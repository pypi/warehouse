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
from pyramid.view import view_config, view_defaults
from sqlalchemy.orm.exc import NoResultFound

from warehouse.accounts.interfaces import IUserService
from warehouse.accounts.models import User
from warehouse.manage.forms import (
    CreateRoleForm, ChangeRoleForm, SaveProfileForm
)
from warehouse.packaging.models import JournalEntry, Role, File
from warehouse.utils.project import confirm_project, remove_project


@view_defaults(
    route_name="manage.profile",
    renderer="manage/profile.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    effective_principals=Authenticated,
)
class ManageProfileViews:
    def __init__(self, request):
        self.request = request
        self.user_service = request.find_service(IUserService, context=None)

    @view_config(request_method="GET")
    def manage_profile(self):
        return {
            'save_profile_form': SaveProfileForm(name=self.request.user.name),
        }

    @view_config(
        request_method="POST",
        request_param=SaveProfileForm.__params__,
    )
    def save_profile(self):
        form = SaveProfileForm(self.request.POST)

        if form.validate():
            self.user_service.update_user(self.request.user.id, **form.data)
            self.request.session.flash(
                'Public profile updated.', queue='success'
            )

        return {
            'save_profile_form': form,
        }


@view_config(
    route_name="manage.projects",
    renderer="manage/projects.html",
    uses_session=True,
    effective_principals=Authenticated,
)
def manage_projects(request):

    def _key(project):
        if project.releases:
            return project.releases[0].created
        return project.created

    return {
        'projects': sorted(request.user.projects, key=_key, reverse=True)
    }


@view_config(
    route_name="manage.project.settings",
    renderer="manage/settings.html",
    uses_session=True,
    permission="manage",
    effective_principals=Authenticated,
)
def manage_project_settings(project, request):
    return {"project": project}


@view_config(
    route_name="manage.project.delete_project",
    uses_session=True,
    require_methods=["POST"],
    permission="manage",
)
def delete_project(project, request):
    confirm_project(project, request, fail_route="manage.project.settings")
    remove_project(project, request)

    return HTTPSeeOther(request.route_path('manage.projects'))


@view_config(
    route_name="manage.project.releases",
    renderer="manage/releases.html",
    uses_session=True,
    permission="manage",
    effective_principals=Authenticated,
)
def manage_project_releases(project, request):
    return {"project": project}


@view_defaults(
    route_name="manage.project.release",
    renderer="manage/release.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    permission="manage",
    effective_principals=Authenticated,
)
class ManageProjectRelease:
    def __init__(self, release, request):
        self.release = release
        self.request = request

    @view_config(request_method="GET")
    def manage_project_release(self):
        return {
            "project": self.release.project,
            "release": self.release,
            "files": self.release.files.all(),
        }

    @view_config(
        request_method="POST",
        request_param=["confirm_version"]
    )
    def delete_project_release(self):
        version = self.request.POST.get('confirm_version')
        if not version:
            self.request.session.flash(
                "Must confirm the request.", queue='error'
            )
            return HTTPSeeOther(
                self.request.route_path(
                    'manage.project.release',
                    project_name=self.release.project.name,
                    version=self.release.version,
                )
            )

        if version != self.release.version:
            self.request.session.flash(
                "Could not delete release - " +
                f"{version!r} is not the same as {self.release.version!r}",
                queue="error",
            )
            return HTTPSeeOther(
                self.request.route_path(
                    'manage.project.release',
                    project_name=self.release.project.name,
                    version=self.release.version,
                )
            )

        self.request.db.add(
            JournalEntry(
                name=self.release.project.name,
                action="remove",
                version=self.release.version,
                submitted_by=self.request.user,
                submitted_from=self.request.remote_addr,
            ),
        )

        self.request.db.delete(self.release)

        self.request.session.flash(
            f"Successfully deleted release {self.release.version!r}.",
            queue="success",
        )

        return HTTPSeeOther(
            self.request.route_path(
                'manage.project.releases',
                project_name=self.release.project.name,
            )
        )

    @view_config(
        request_method="POST",
        request_param=["confirm_filename", "file_id"]
    )
    def delete_project_release_file(self):
        filename = self.request.POST.get('confirm_filename')
        if not filename:
            self.request.session.flash(
                "Must confirm the request.", queue='error'
            )
            return HTTPSeeOther(
                self.request.route_path(
                    'manage.project.release',
                    project_name=self.release.project.name,
                    version=self.release.version,
                )
            )

        release_file = (
            self.request.db.query(File)
            .filter(
                File.name == self.release.project.name,
                File.id == self.request.POST.get('file_id'),
            )
            .one()
        )

        if filename != release_file.filename:
            self.request.session.flash(
                "Could not delete file - " +
                f"{filename!r} is not the same as {release_file.filename!r}",
                queue="error",
            )
            return HTTPSeeOther(
                self.request.route_path(
                    'manage.project.release',
                    project_name=self.release.project.name,
                    version=self.release.version,
                )
            )

        self.request.db.add(
            JournalEntry(
                name=self.release.project.name,
                action=f"remove file {release_file.filename}",
                version=self.release.version,
                submitted_by=self.request.user,
                submitted_from=self.request.remote_addr,
            ),
        )

        self.request.db.delete(release_file)

        self.request.session.flash(
            f"Successfully deleted file {release_file.filename!r}.",
            queue="success",
        )

        return HTTPSeeOther(
            self.request.route_path(
                'manage.project.release',
                project_name=self.release.project.name,
                version=self.release.version,
            )
        )


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
        request.route_path('manage.project.roles', project_name=project.name)
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
        request.route_path('manage.project.roles', project_name=project.name)
    )
