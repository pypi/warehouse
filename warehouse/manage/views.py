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
from sqlalchemy import func
from sqlalchemy.orm.exc import NoResultFound

from warehouse.accounts.interfaces import IUserService
from warehouse.accounts.models import User, Email
from warehouse.accounts.views import logout
from warehouse.email import (
    send_account_deletion_email, send_added_as_collaborator_email,
    send_collaborator_added_email, send_email_verification_email,
    send_password_change_email, send_primary_email_change_email
)
from warehouse.manage.forms import (
    AddEmailForm, ChangePasswordForm, CreateRoleForm, ChangeRoleForm,
    SaveAccountForm,
)
from warehouse.packaging.models import (
    File, JournalEntry, Project, Release, Role,
)
from warehouse.utils.project import (
    confirm_project,
    destroy_docs,
    remove_project,
)


@view_defaults(
    route_name="manage.account",
    renderer="manage/account.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    effective_principals=Authenticated,
)
class ManageAccountViews:
    def __init__(self, request):
        self.request = request
        self.user_service = request.find_service(IUserService, context=None)

    @property
    def active_projects(self):
        ''' Return all the projects for with the user is a sole owner '''
        projects_owned = (
            self.request.db.query(Project)
            .join(Role.project)
            .filter(Role.role_name == 'Owner', Role.user == self.request.user)
            .subquery()
        )

        with_sole_owner = (
            self.request.db.query(Role.package_name)
            .join(projects_owned)
            .filter(Role.role_name == 'Owner')
            .group_by(Role.package_name)
            .having(func.count(Role.package_name) == 1)
            .subquery()
        )

        return (
            self.request.db.query(Project)
            .join(with_sole_owner)
            .order_by(Project.name)
            .all()
        )

    @property
    def default_response(self):
        return {
            'save_account_form': SaveAccountForm(name=self.request.user.name),
            'add_email_form': AddEmailForm(user_service=self.user_service),
            'change_password_form': ChangePasswordForm(
                user_service=self.user_service
            ),
            'active_projects': self.active_projects,
        }

    @view_config(request_method="GET")
    def manage_account(self):
        return self.default_response

    @view_config(
        request_method="POST",
        request_param=SaveAccountForm.__params__,
    )
    def save_account(self):
        form = SaveAccountForm(self.request.POST)

        if form.validate():
            self.user_service.update_user(self.request.user.id, **form.data)
            self.request.session.flash(
                'Account details updated.', queue='success'
            )

        return {
            **self.default_response,
            'save_account_form': form,
        }

    @view_config(
        request_method="POST",
        request_param=AddEmailForm.__params__,
    )
    def add_email(self):
        form = AddEmailForm(self.request.POST, user_service=self.user_service)

        if form.validate():
            email = self.user_service.add_email(
                self.request.user.id, form.email.data,
            )

            send_email_verification_email(
                self.request,
                self.request.user,
                email,
            )

            self.request.session.flash(
                f'Email {email.email} added - check your email for ' +
                'a verification link.',
                queue='success',
            )
            return self.default_response

        return {
            **self.default_response,
            'add_email_form': form,
        }

    @view_config(
        request_method="POST",
        request_param=["delete_email_id"],
    )
    def delete_email(self):
        try:
            email = self.request.db.query(Email).filter(
                Email.id == self.request.POST['delete_email_id'],
                Email.user_id == self.request.user.id,
            ).one()
        except NoResultFound:
            self.request.session.flash(
                'Email address not found.', queue='error'
            )
            return self.default_response

        if email.primary:
            self.request.session.flash(
                'Cannot remove primary email address.', queue='error'
            )
        else:
            self.request.user.emails.remove(email)
            self.request.session.flash(
                f'Email address {email.email} removed.', queue='success'
            )
        return self.default_response

    @view_config(
        request_method="POST",
        request_param=["primary_email_id"],
    )
    def change_primary_email(self):
        previous_primary_email = self.request.user.email
        try:
            new_primary_email = self.request.db.query(Email).filter(
                Email.user_id == self.request.user.id,
                Email.id == self.request.POST['primary_email_id'],
                Email.verified.is_(True),
            ).one()
        except NoResultFound:
            self.request.session.flash(
                'Email address not found.', queue='error'
            )
            return self.default_response

        self.request.db.query(Email).filter(
            Email.user_id == self.request.user.id,
            Email.primary.is_(True),
        ).update(values={'primary': False})

        new_primary_email.primary = True

        self.request.session.flash(
            f'Email address {new_primary_email.email} set as primary.',
            queue='success',
        )

        send_primary_email_change_email(
            self.request, self.request.user, previous_primary_email
        )
        return self.default_response

    @view_config(
        request_method="POST",
        request_param=['reverify_email_id'],
    )
    def reverify_email(self):
        try:
            email = self.request.db.query(Email).filter(
                Email.id == self.request.POST['reverify_email_id'],
                Email.user_id == self.request.user.id,
            ).one()
        except NoResultFound:
            self.request.session.flash(
                'Email address not found.', queue='error'
            )
            return self.default_response

        if email.verified:
            self.request.session.flash(
                'Email is already verified.', queue='error'
            )
        else:
            send_email_verification_email(
                self.request,
                self.request.user,
                email,
            )

            self.request.session.flash(
                f'Verification email for {email.email} resent.',
                queue='success',
            )

        return self.default_response

    @view_config(
        request_method='POST',
        request_param=ChangePasswordForm.__params__,
    )
    def change_password(self):
        form = ChangePasswordForm(
            **self.request.POST,
            username=self.request.user.username,
            full_name=self.request.user.name,
            email=self.request.user.email,
            user_service=self.user_service,
        )

        if form.validate():
            self.user_service.update_user(
                self.request.user.id,
                password=form.new_password.data,
            )
            send_password_change_email(self.request, self.request.user)
            self.request.session.flash(
                'Password updated.', queue='success'
            )

        return {
            **self.default_response,
            'change_password_form': form,
        }

    @view_config(
        request_method='POST',
        request_param=['confirm_username']
    )
    def delete_account(self):
        username = self.request.params.get('confirm_username')

        if not username:
            self.request.session.flash(
                "Must confirm the request.", queue='error'
            )
            return self.default_response

        if username != self.request.user.username:
            self.request.session.flash(
                f"Could not delete account - {username!r} is not the same as "
                f"{self.request.user.username!r}",
                queue='error'
            )
            return self.default_response

        if self.active_projects:
            self.request.session.flash(
                "Cannot delete account with active project ownerships.",
                queue='error',
            )
            return self.default_response

        # Update all journals to point to `deleted-user` instead
        deleted_user = (
            self.request.db.query(User)
            .filter(User.username == 'deleted-user')
            .one()
        )

        journals = (
            self.request.db.query(JournalEntry)
            .filter(JournalEntry.submitted_by == self.request.user)
            .all()
        )

        for journal in journals:
            journal.submitted_by = deleted_user

        # Send a notification email
        send_account_deletion_email(self.request, self.request.user)

        # Actually delete the user
        self.request.db.delete(self.request.user)

        return logout(self.request)


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

    projects_owned = set(
        project.name
        for project in (
            request.db.query(Project.name)
            .join(Role.project)
            .filter(Role.role_name == 'Owner', Role.user == request.user)
            .all()
        )
    )

    return {
        'projects': sorted(request.user.projects, key=_key, reverse=True),
        'projects_owned': projects_owned,
    }


@view_config(
    route_name="manage.project.settings",
    context=Project,
    renderer="manage/settings.html",
    uses_session=True,
    permission="manage",
    effective_principals=Authenticated,
)
def manage_project_settings(project, request):
    return {"project": project}


@view_config(
    route_name="manage.project.delete_project",
    context=Project,
    uses_session=True,
    require_methods=["POST"],
    permission="manage",
)
def delete_project(project, request):
    confirm_project(project, request, fail_route="manage.project.settings")
    remove_project(project, request)

    return HTTPSeeOther(request.route_path('manage.projects'))


@view_config(
    route_name="manage.project.destroy_docs",
    context=Project,
    uses_session=True,
    require_methods=["POST"],
    permission="manage",
)
def destroy_project_docs(project, request):
    confirm_project(
        project, request, fail_route="manage.project.documentation"
    )
    destroy_docs(project, request)

    return HTTPSeeOther(
        request.route_path(
            'manage.project.documentation',
            project_name=project.normalized_name,
        )
    )


@view_config(
    route_name="manage.project.releases",
    context=Project,
    renderer="manage/releases.html",
    uses_session=True,
    permission="manage",
    effective_principals=Authenticated,
)
def manage_project_releases(project, request):
    return {"project": project}


@view_defaults(
    route_name="manage.project.release",
    context=Release,
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
        request_param=["confirm_project_name", "file_id"]
    )
    def delete_project_release_file(self):

        def _error(message):
            self.request.session.flash(message, queue='error')
            return HTTPSeeOther(
                self.request.route_path(
                    'manage.project.release',
                    project_name=self.release.project.name,
                    version=self.release.version,
                )
            )

        project_name = self.request.POST.get('confirm_project_name')

        if not project_name:
            return _error("Must confirm the request.")

        try:
            release_file = (
                self.request.db.query(File)
                .filter(
                    File.name == self.release.project.name,
                    File.id == self.request.POST.get('file_id'),
                )
                .one()
            )
        except NoResultFound:
            return _error('Could not find file.')

        if project_name != self.release.project.name:
            return _error(
                "Could not delete file - " +
                f"{project_name!r} is not the same as "
                f"{self.release.project.name!r}",
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
    context=Project,
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

            owners = (
                request.db.query(Role)
                .join(Role.user)
                .filter(Role.role_name == 'Owner', Role.project == project)
            )
            owner_users = [owner.user for owner in owners]
            owner_users.remove(request.user)

            send_collaborator_added_email(
                request,
                user,
                request.user,
                project.name,
                form.role_name.data,
                owner_users,
            )

            send_added_as_collaborator_email(
                request,
                request.user,
                project.name,
                form.role_name.data,
                user,
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
    context=Project,
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
    context=Project,
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


@view_config(
    route_name="manage.project.history",
    context=Project,
    renderer="manage/history.html",
    uses_session=True,
    permission="manage",
)
def manage_project_history(project, request):
    journals = (
        request.db.query(JournalEntry)
        .filter(JournalEntry.name == project.name)
        .order_by(JournalEntry.submitted_date.desc(), JournalEntry.id.desc())
        .all()
    )
    return {
        'project': project,
        'journals': journals,
    }


@view_config(
    route_name="manage.project.documentation",
    context=Project,
    renderer="manage/documentation.html",
    uses_session=True,
    permission="manage",
)
def manage_project_documentation(project, request):
    return {
        'project': project,
    }
