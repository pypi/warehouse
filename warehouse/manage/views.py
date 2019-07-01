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

import base64
import io

from collections import defaultdict

import pyqrcode

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPSeeOther
from pyramid.response import Response
from pyramid.view import view_config, view_defaults
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import NoResultFound

import warehouse.utils.otp as otp

from warehouse.accounts.interfaces import IPasswordBreachedService, IUserService
from warehouse.accounts.models import Email, User
from warehouse.accounts.views import logout
from warehouse.email import (
    send_account_deletion_email,
    send_added_as_collaborator_email,
    send_collaborator_added_email,
    send_email_verification_email,
    send_password_change_email,
    send_primary_email_change_email,
)
from warehouse.manage.forms import (
    AddEmailForm,
    ChangePasswordForm,
    ChangeRoleForm,
    CreateRoleForm,
    DeleteTOTPForm,
    DeleteWebAuthnForm,
    ProvisionTOTPForm,
    ProvisionWebAuthnForm,
    SaveAccountForm,
)
from warehouse.packaging.models import File, JournalEntry, Project, Release, Role
from warehouse.utils.paginate import paginate_url_factory
from warehouse.utils.project import confirm_project, destroy_docs, remove_project


def user_projects(request):
    """ Return all the projects for which the user is a sole owner """
    projects_owned = (
        request.db.query(Project.id)
        .join(Role.project)
        .filter(Role.role_name == "Owner", Role.user == request.user)
        .subquery()
    )

    with_sole_owner = (
        request.db.query(Role.project_id)
        .join(projects_owned)
        .filter(Role.role_name == "Owner")
        .group_by(Role.project_id)
        .having(func.count(Role.project_id) == 1)
        .subquery()
    )

    return {
        "projects_owned": (
            request.db.query(Project)
            .join(projects_owned, Project.id == projects_owned.c.id)
            .order_by(Project.name)
            .all()
        ),
        "projects_sole_owned": (
            request.db.query(Project).join(with_sole_owner).order_by(Project.name).all()
        ),
    }


@view_defaults(
    route_name="manage.account",
    renderer="manage/account.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    permission="manage:user",
)
class ManageAccountViews:
    def __init__(self, request):
        self.request = request
        self.user_service = request.find_service(IUserService, context=None)
        self.breach_service = request.find_service(
            IPasswordBreachedService, context=None
        )

    @property
    def active_projects(self):
        return user_projects(request=self.request)["projects_sole_owned"]

    @property
    def default_response(self):
        return {
            "save_account_form": SaveAccountForm(name=self.request.user.name),
            "add_email_form": AddEmailForm(
                user_service=self.user_service, user_id=self.request.user.id
            ),
            "change_password_form": ChangePasswordForm(
                user_service=self.user_service, breach_service=self.breach_service
            ),
            "active_projects": self.active_projects,
        }

    @view_config(request_method="GET")
    def manage_account(self):
        return self.default_response

    @view_config(request_method="POST", request_param=SaveAccountForm.__params__)
    def save_account(self):
        form = SaveAccountForm(self.request.POST)

        if form.validate():
            self.user_service.update_user(self.request.user.id, **form.data)
            self.request.session.flash("Account details updated", queue="success")

        return {**self.default_response, "save_account_form": form}

    @view_config(request_method="POST", request_param=AddEmailForm.__params__)
    def add_email(self):
        form = AddEmailForm(
            self.request.POST,
            user_service=self.user_service,
            user_id=self.request.user.id,
        )

        if form.validate():
            email = self.user_service.add_email(self.request.user.id, form.email.data)

            send_email_verification_email(self.request, (self.request.user, email))

            self.request.session.flash(
                f"Email {email.email} added - check your email for "
                + "a verification link",
                queue="success",
            )
            return self.default_response

        return {**self.default_response, "add_email_form": form}

    @view_config(request_method="POST", request_param=["delete_email_id"])
    def delete_email(self):
        try:
            email = (
                self.request.db.query(Email)
                .filter(
                    Email.id == self.request.POST["delete_email_id"],
                    Email.user_id == self.request.user.id,
                )
                .one()
            )
        except NoResultFound:
            self.request.session.flash("Email address not found", queue="error")
            return self.default_response

        if email.primary:
            self.request.session.flash(
                "Cannot remove primary email address", queue="error"
            )
        else:
            self.request.user.emails.remove(email)
            self.request.session.flash(
                f"Email address {email.email} removed", queue="success"
            )
        return self.default_response

    @view_config(request_method="POST", request_param=["primary_email_id"])
    def change_primary_email(self):
        previous_primary_email = self.request.user.primary_email
        try:
            new_primary_email = (
                self.request.db.query(Email)
                .filter(
                    Email.user_id == self.request.user.id,
                    Email.id == self.request.POST["primary_email_id"],
                    Email.verified.is_(True),
                )
                .one()
            )
        except NoResultFound:
            self.request.session.flash("Email address not found", queue="error")
            return self.default_response

        self.request.db.query(Email).filter(
            Email.user_id == self.request.user.id, Email.primary.is_(True)
        ).update(values={"primary": False})

        new_primary_email.primary = True

        self.request.session.flash(
            f"Email address {new_primary_email.email} set as primary", queue="success"
        )

        if previous_primary_email is not None:
            send_primary_email_change_email(
                self.request, (self.request.user, previous_primary_email)
            )
        return self.default_response

    @view_config(request_method="POST", request_param=["reverify_email_id"])
    def reverify_email(self):
        try:
            email = (
                self.request.db.query(Email)
                .filter(
                    Email.id == self.request.POST["reverify_email_id"],
                    Email.user_id == self.request.user.id,
                )
                .one()
            )
        except NoResultFound:
            self.request.session.flash("Email address not found", queue="error")
            return self.default_response

        if email.verified:
            self.request.session.flash("Email is already verified", queue="error")
        else:
            send_email_verification_email(self.request, (self.request.user, email))

            self.request.session.flash(
                f"Verification email for {email.email} resent", queue="success"
            )

        return self.default_response

    @view_config(request_method="POST", request_param=ChangePasswordForm.__params__)
    def change_password(self):
        form = ChangePasswordForm(
            **self.request.POST,
            username=self.request.user.username,
            full_name=self.request.user.name,
            email=self.request.user.email,
            user_service=self.user_service,
            breach_service=self.breach_service,
            check_password_metrics_tags=["method:new_password"],
        )

        if form.validate():
            self.user_service.update_user(
                self.request.user.id, password=form.new_password.data
            )
            send_password_change_email(self.request, self.request.user)
            self.request.session.flash("Password updated", queue="success")

        return {**self.default_response, "change_password_form": form}

    @view_config(request_method="POST", request_param=["confirm_username"])
    def delete_account(self):
        username = self.request.params.get("confirm_username")

        if not username:
            self.request.session.flash("Confirm the request", queue="error")
            return self.default_response

        if username != self.request.user.username:
            self.request.session.flash(
                f"Could not delete account - {username!r} is not the same as "
                f"{self.request.user.username!r}",
                queue="error",
            )
            return self.default_response

        if self.active_projects:
            self.request.session.flash(
                "Cannot delete account with active project ownerships", queue="error"
            )
            return self.default_response

        # Update all journals to point to `deleted-user` instead
        deleted_user = (
            self.request.db.query(User).filter(User.username == "deleted-user").one()
        )

        journals = (
            self.request.db.query(JournalEntry)
            .options(joinedload("submitted_by"))
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


@view_defaults(
    route_name="manage.account.totp-provision",
    renderer="manage/account/totp-provision.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    permission="manage:user",
    http_cache=0,
)
class ProvisionTOTPViews:
    def __init__(self, request):
        self.request = request
        self.user_service = request.find_service(IUserService, context=None)

    @property
    def default_response(self):
        totp_secret = self.request.session.get_totp_secret()
        return {
            "provision_totp_secret": base64.b32encode(totp_secret).decode(),
            "provision_totp_form": ProvisionTOTPForm(totp_secret=totp_secret),
            "provision_totp_uri": otp.generate_totp_provisioning_uri(
                totp_secret,
                self.request.user.username,
                issuer_name=self.request.registry.settings["site.name"],
            ),
        }

    @view_config(route_name="manage.account.totp-provision.image", request_method="GET")
    def generate_totp_qr(self):
        if not self.request.user.two_factor_provisioning_allowed:
            self.request.session.flash(
                "Modifying 2FA requires a verified email.", queue="error"
            )
            return Response(status=403)

        totp_secret = self.user_service.get_totp_secret(self.request.user.id)
        if totp_secret:
            return Response(status=403)

        totp_qr = pyqrcode.create(self.default_response["provision_totp_uri"])
        qr_buffer = io.BytesIO()
        totp_qr.svg(qr_buffer, scale=5)

        return Response(content_type="image/svg+xml", body=qr_buffer.getvalue())

    @view_config(request_method="GET")
    def totp_provision(self):
        if not self.request.user.two_factor_provisioning_allowed:
            self.request.session.flash(
                "Modifying 2FA requires a verified email.", queue="error"
            )
            return Response(status=403)

        totp_secret = self.user_service.get_totp_secret(self.request.user.id)
        if totp_secret:
            self.request.session.flash("TOTP already provisioned.", queue="error")
            return HTTPSeeOther(self.request.route_path("manage.account"))

        return self.default_response

    @view_config(request_method="POST", request_param=ProvisionTOTPForm.__params__)
    def validate_totp_provision(self):
        if not self.request.user.two_factor_provisioning_allowed:
            self.request.session.flash(
                "Modifying 2FA requires a verified email.", queue="error"
            )
            return Response(status=403)

        totp_secret = self.user_service.get_totp_secret(self.request.user.id)
        if totp_secret:
            self.request.session.flash("TOTP already provisioned.", queue="error")
            return HTTPSeeOther(self.request.route_path("manage.account"))

        form = ProvisionTOTPForm(
            **self.request.POST, totp_secret=self.request.session.get_totp_secret()
        )

        if form.validate():
            self.user_service.update_user(
                self.request.user.id, totp_secret=self.request.session.get_totp_secret()
            )

            self.request.session.clear_totp_secret()
            self.request.session.flash(
                "TOTP application successfully provisioned.", queue="success"
            )

            return HTTPSeeOther(self.request.route_path("manage.account"))

        return {**self.default_response, "provision_totp_form": form}

    @view_config(request_method="POST", request_param=DeleteTOTPForm.__params__)
    def delete_totp(self):
        if not self.request.user.two_factor_provisioning_allowed:
            self.request.session.flash(
                "Modifying 2FA requires a verified email.", queue="error"
            )
            return Response(status=403)

        totp_secret = self.user_service.get_totp_secret(self.request.user.id)
        if not totp_secret:
            self.request.session.flash("No TOTP application to delete.", queue="error")
            return HTTPSeeOther(self.request.route_path("manage.account"))

        form = DeleteTOTPForm(
            **self.request.POST,
            username=self.request.user.username,
            user_service=self.user_service,
        )

        if form.validate():
            self.user_service.update_user(self.request.user.id, totp_secret=None)
            self.request.session.flash("TOTP application deleted.", queue="success")
        else:
            self.request.session.flash("Invalid credentials.", queue="error")

        return HTTPSeeOther(self.request.route_path("manage.account"))


@view_defaults(
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    permission="manage:user",
    http_cache=0,
)
class ProvisionWebAuthnViews:
    def __init__(self, request):
        self.request = request
        self.user_service = request.find_service(IUserService, context=None)

    @view_config(
        request_method="GET",
        route_name="manage.account.webauthn-provision",
        renderer="manage/account/webauthn-provision.html",
    )
    def webauthn_provision(self):
        return {}

    @view_config(
        request_method="GET",
        route_name="manage.account.webauthn-provision.options",
        renderer="json",
    )
    def webauthn_provision_options(self):
        return self.user_service.get_webauthn_credential_options(
            self.request.user.id,
            challenge=self.request.session.get_webauthn_challenge(),
            rp_name=self.request.registry.settings["site.name"],
            rp_id=self.request.domain,
            icon_url=self.request.registry.settings.get(
                "warehouse.domain", self.request.domain
            ),
        )

    @view_config(
        request_method="POST",
        request_param=ProvisionWebAuthnForm.__params__,
        route_name="manage.account.webauthn-provision.validate",
        renderer="json",
    )
    def validate_webauthn_provision(self):
        form = ProvisionWebAuthnForm(
            **self.request.POST,
            user_service=self.user_service,
            user_id=self.request.user.id,
            challenge=self.request.session.get_webauthn_challenge(),
            rp_id=self.request.domain,
            origin=self.request.host_url,
        )

        self.request.session.clear_webauthn_challenge()

        if form.validate():
            self.user_service.add_webauthn(
                self.request.user.id,
                label=form.label.data,
                credential_id=form.validated_credential.credential_id.decode(),
                public_key=form.validated_credential.public_key.decode(),
                sign_count=form.validated_credential.sign_count,
            )
            self.request.session.flash(
                "WebAuthn successfully provisioned.", queue="success"
            )
            return {"success": "WebAuthn successfully provisioned"}

        errors = [
            str(error) for error_list in form.errors.values() for error in error_list
        ]
        return {"fail": {"errors": errors}}

    @view_config(
        request_method="POST",
        request_param=DeleteWebAuthnForm.__params__,
        route_name="manage.account.webauthn-provision.delete",
    )
    def delete_webauthn(self):
        if len(self.request.user.webauthn) == 0:
            self.request.session.flash("No WebAuthhn device to delete.", queue="error")
            return HTTPSeeOther(self.request.route_path("manage.account"))

        form = DeleteWebAuthnForm(
            **self.request.POST,
            username=self.request.user.username,
            user_service=self.user_service,
            user_id=self.request.user.id,
        )

        if form.validate():
            self.request.user.webauthn.remove(form.webauthn)
            self.request.session.flash("WebAuthn device deleted.", queue="success")
        else:
            self.request.session.flash("Invalid credentials.", queue="error")

        return HTTPSeeOther(self.request.route_path("manage.account"))


@view_config(
    route_name="manage.projects",
    renderer="manage/projects.html",
    uses_session=True,
    permission="manage:user",
)
def manage_projects(request):
    def _key(project):
        if project.releases:
            return project.releases[0].created
        return project.created

    all_user_projects = user_projects(request)
    projects_owned = set(
        project.name for project in all_user_projects["projects_owned"]
    )
    projects_sole_owned = set(
        project.name for project in all_user_projects["projects_sole_owned"]
    )

    return {
        "projects": sorted(request.user.projects, key=_key, reverse=True),
        "projects_owned": projects_owned,
        "projects_sole_owned": projects_sole_owned,
    }


@view_config(
    route_name="manage.project.settings",
    context=Project,
    renderer="manage/settings.html",
    uses_session=True,
    permission="manage:project",
)
def manage_project_settings(project, request):
    return {"project": project}


@view_config(
    route_name="manage.project.delete_project",
    context=Project,
    uses_session=True,
    require_methods=["POST"],
    permission="manage:project",
)
def delete_project(project, request):
    confirm_project(project, request, fail_route="manage.project.settings")
    remove_project(project, request)

    return HTTPSeeOther(request.route_path("manage.projects"))


@view_config(
    route_name="manage.project.destroy_docs",
    context=Project,
    uses_session=True,
    require_methods=["POST"],
    permission="manage:project",
)
def destroy_project_docs(project, request):
    confirm_project(project, request, fail_route="manage.project.documentation")
    destroy_docs(project, request)

    return HTTPSeeOther(
        request.route_path(
            "manage.project.documentation", project_name=project.normalized_name
        )
    )


@view_config(
    route_name="manage.project.releases",
    context=Project,
    renderer="manage/releases.html",
    uses_session=True,
    permission="manage:project",
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
    permission="manage:project",
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

    @view_config(request_method="POST", request_param=["confirm_version"])
    def delete_project_release(self):
        version = self.request.POST.get("confirm_version")
        if not version:
            self.request.session.flash("Confirm the request", queue="error")
            return HTTPSeeOther(
                self.request.route_path(
                    "manage.project.release",
                    project_name=self.release.project.name,
                    version=self.release.version,
                )
            )

        if version != self.release.version:
            self.request.session.flash(
                "Could not delete release - "
                + f"{version!r} is not the same as {self.release.version!r}",
                queue="error",
            )
            return HTTPSeeOther(
                self.request.route_path(
                    "manage.project.release",
                    project_name=self.release.project.name,
                    version=self.release.version,
                )
            )

        self.request.db.add(
            JournalEntry(
                name=self.release.project.name,
                action="remove release",
                version=self.release.version,
                submitted_by=self.request.user,
                submitted_from=self.request.remote_addr,
            )
        )

        self.request.db.delete(self.release)

        self.request.session.flash(
            f"Deleted release {self.release.version!r}", queue="success"
        )

        return HTTPSeeOther(
            self.request.route_path(
                "manage.project.releases", project_name=self.release.project.name
            )
        )

    @view_config(
        request_method="POST", request_param=["confirm_project_name", "file_id"]
    )
    def delete_project_release_file(self):
        def _error(message):
            self.request.session.flash(message, queue="error")
            return HTTPSeeOther(
                self.request.route_path(
                    "manage.project.release",
                    project_name=self.release.project.name,
                    version=self.release.version,
                )
            )

        project_name = self.request.POST.get("confirm_project_name")

        if not project_name:
            return _error("Confirm the request")

        try:
            release_file = (
                self.request.db.query(File)
                .filter(
                    File.release == self.release,
                    File.id == self.request.POST.get("file_id"),
                )
                .one()
            )
        except NoResultFound:
            return _error("Could not find file")

        if project_name != self.release.project.name:
            return _error(
                "Could not delete file - " + f"{project_name!r} is not the same as "
                f"{self.release.project.name!r}"
            )

        self.request.db.add(
            JournalEntry(
                name=self.release.project.name,
                action=f"remove file {release_file.filename}",
                version=self.release.version,
                submitted_by=self.request.user,
                submitted_from=self.request.remote_addr,
            )
        )

        self.request.db.delete(release_file)

        self.request.session.flash(
            f"Deleted file {release_file.filename!r}", queue="success"
        )

        return HTTPSeeOther(
            self.request.route_path(
                "manage.project.release",
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
    permission="manage:project",
)
def manage_project_roles(project, request, _form_class=CreateRoleForm):
    user_service = request.find_service(IUserService, context=None)
    form = _form_class(request.POST, user_service=user_service)

    if request.method == "POST" and form.validate():
        username = form.username.data
        role_name = form.role_name.data
        userid = user_service.find_userid(username)
        user = user_service.get_user(userid)

        if request.db.query(
            request.db.query(Role)
            .filter(
                Role.user == user, Role.project == project, Role.role_name == role_name
            )
            .exists()
        ).scalar():
            request.session.flash(
                f"User '{username}' already has {role_name} role for project",
                queue="error",
            )
        elif user.primary_email is None or not user.primary_email.verified:
            request.session.flash(
                f"User '{username}' does not have a verified primary email "
                f"address and cannot be added as a {role_name} for project.",
                queue="error",
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
                )
            )

            owner_roles = (
                request.db.query(Role)
                .join(Role.user)
                .filter(Role.role_name == "Owner", Role.project == project)
            )
            owner_users = {owner.user for owner in owner_roles}

            # Don't send to the owner that added the new role
            owner_users.discard(request.user)

            # Don't send owners email to new user if they are now an owner
            owner_users.discard(user)

            send_collaborator_added_email(
                request,
                owner_users,
                user=user,
                submitter=request.user,
                project_name=project.name,
                role=form.role_name.data,
            )

            send_added_as_collaborator_email(
                request,
                user,
                submitter=request.user,
                project_name=project.name,
                role=form.role_name.data,
            )

            request.session.flash(
                f"Added collaborator '{form.username.data}'", queue="success"
            )
        form = _form_class(user_service=user_service)

    roles = request.db.query(Role).join(User).filter(Role.project == project).all()

    # TODO: The following lines are a hack to handle multiple roles for a
    # single user and should be removed when fixing GH-2745
    roles_by_user = defaultdict(list)
    for role in roles:
        roles_by_user[role.user.username].append(role)

    return {"project": project, "roles_by_user": roles_by_user, "form": form}


@view_config(
    route_name="manage.project.change_role",
    context=Project,
    uses_session=True,
    require_methods=["POST"],
    permission="manage:project",
)
def change_project_role(project, request, _form_class=ChangeRoleForm):
    # TODO: This view was modified to handle deleting multiple roles for a
    # single user and should be updated when fixing GH-2745

    form = _form_class(request.POST)

    if form.validate():
        role_ids = request.POST.getall("role_id")

        if len(role_ids) > 1:
            # This user has more than one role, so just delete all the ones
            # that aren't what we want.
            #
            # TODO: This branch should be removed when fixing GH-2745.
            roles = (
                request.db.query(Role)
                .join(User)
                .filter(
                    Role.id.in_(role_ids),
                    Role.project == project,
                    Role.role_name != form.role_name.data,
                )
                .all()
            )
            removing_self = any(
                role.role_name == "Owner" and role.user == request.user
                for role in roles
            )
            if removing_self:
                request.session.flash("Cannot remove yourself as Owner", queue="error")
            else:
                for role in roles:
                    request.db.delete(role)
                    request.db.add(
                        JournalEntry(
                            name=project.name,
                            action=f"remove {role.role_name} {role.user.username}",
                            submitted_by=request.user,
                            submitted_from=request.remote_addr,
                        )
                    )
                request.session.flash("Changed role", queue="success")
        else:
            # This user only has one role, so get it and change the type.
            try:
                role = (
                    request.db.query(Role)
                    .join(User)
                    .filter(
                        Role.id == request.POST.get("role_id"), Role.project == project
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
                                role.role_name, role.user.username, form.role_name.data
                            ),
                            submitted_by=request.user,
                            submitted_from=request.remote_addr,
                        )
                    )
                    role.role_name = form.role_name.data
                    request.session.flash("Changed role", queue="success")
            except NoResultFound:
                request.session.flash("Could not find role", queue="error")

    return HTTPSeeOther(
        request.route_path("manage.project.roles", project_name=project.name)
    )


@view_config(
    route_name="manage.project.delete_role",
    context=Project,
    uses_session=True,
    require_methods=["POST"],
    permission="manage:project",
)
def delete_project_role(project, request):
    # TODO: This view was modified to handle deleting multiple roles for a
    # single user and should be updated when fixing GH-2745

    roles = (
        request.db.query(Role)
        .join(User)
        .filter(Role.id.in_(request.POST.getall("role_id")), Role.project == project)
        .all()
    )
    removing_self = any(
        role.role_name == "Owner" and role.user == request.user for role in roles
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
                    action=f"remove {role.role_name} {role.user.username}",
                    submitted_by=request.user,
                    submitted_from=request.remote_addr,
                )
            )
        request.session.flash("Removed role", queue="success")

    return HTTPSeeOther(
        request.route_path("manage.project.roles", project_name=project.name)
    )


@view_config(
    route_name="manage.project.history",
    context=Project,
    renderer="manage/history.html",
    uses_session=True,
    permission="manage:project",
)
def manage_project_history(project, request):
    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.")

    journals_query = (
        request.db.query(JournalEntry)
        .options(joinedload("submitted_by"))
        .filter(JournalEntry.name == project.name)
        .order_by(JournalEntry.submitted_date.desc(), JournalEntry.id.desc())
    )

    journals = SQLAlchemyORMPage(
        journals_query,
        page=page_num,
        items_per_page=25,
        url_maker=paginate_url_factory(request),
    )

    if journals.page_count and page_num > journals.page_count:
        raise HTTPNotFound

    return {"project": project, "journals": journals}


@view_config(
    route_name="manage.project.documentation",
    context=Project,
    renderer="manage/documentation.html",
    uses_session=True,
    permission="manage:project",
)
def manage_project_documentation(project, request):
    return {"project": project}
