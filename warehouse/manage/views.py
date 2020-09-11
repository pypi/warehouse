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

import pyqrcode

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import HTTPBadRequest, HTTPNotFound, HTTPSeeOther
from pyramid.response import Response
from pyramid.view import view_config, view_defaults
from sqlalchemy import func
from sqlalchemy.orm import Load, joinedload
from sqlalchemy.orm.exc import NoResultFound

import warehouse.utils.otp as otp

from warehouse.accounts.interfaces import (
    IPasswordBreachedService,
    ITokenService,
    IUserService,
    TokenExpired,
)
from warehouse.accounts.models import Email, User
from warehouse.accounts.views import logout
from warehouse.admin.flags import AdminFlagValue
from warehouse.email import (
    send_account_deletion_email,
    send_collaborator_removed_email,
    send_collaborator_role_changed_email,
    send_email_verification_email,
    send_password_change_email,
    send_primary_email_change_email,
    send_project_role_verification_email,
    send_removed_as_collaborator_email,
    send_removed_project_email,
    send_removed_project_release_email,
    send_removed_project_release_file_email,
    send_role_changed_as_collaborator_email,
    send_two_factor_added_email,
    send_two_factor_removed_email,
    send_unyanked_project_release_email,
    send_yanked_project_release_email,
)
from warehouse.forklift.legacy import MAX_FILESIZE, MAX_PROJECT_SIZE
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.manage.forms import (
    AddEmailForm,
    ChangePasswordForm,
    ChangeRoleForm,
    ConfirmPasswordForm,
    CreateMacaroonForm,
    CreateRoleForm,
    DeleteMacaroonForm,
    DeleteTOTPForm,
    DeleteWebAuthnForm,
    ProvisionTOTPForm,
    ProvisionWebAuthnForm,
    SaveAccountForm,
)
from warehouse.packaging.models import (
    File,
    JournalEntry,
    Project,
    ProjectEvent,
    Release,
    Role,
    RoleInvitation,
    RoleInvitationStatus,
)
from warehouse.utils.http import is_safe_url
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
    has_translations=True,
    require_reauth=True,
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
            "save_account_form": SaveAccountForm(
                name=self.request.user.name,
                public_email=getattr(self.request.user.public_email, "email", ""),
                user_service=self.user_service,
                user_id=self.request.user.id,
            ),
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

    @view_config(request_method="POST", request_param=["name"])
    def save_account(self):
        form = SaveAccountForm(
            self.request.POST,
            user_service=self.user_service,
            user_id=self.request.user.id,
        )

        if form.validate():
            data = form.data
            public_email = data.pop("public_email", "")
            self.user_service.update_user(self.request.user.id, **data)
            for email in self.request.user.emails:
                email.public = email.email == public_email
            self.request.session.flash("Account details updated", queue="success")

        return {**self.default_response, "save_account_form": form}

    @view_config(
        request_method="POST",
        request_param=AddEmailForm.__params__,
        require_reauth=True,
    )
    def add_email(self):
        form = AddEmailForm(
            self.request.POST,
            user_service=self.user_service,
            user_id=self.request.user.id,
        )

        if form.validate():
            email = self.user_service.add_email(
                self.request.user.id, form.email.data, self.request.remote_addr
            )
            self.user_service.record_event(
                self.request.user.id,
                tag="account:email:add",
                ip_address=self.request.remote_addr,
                additional={"email": email.email},
            )

            send_email_verification_email(self.request, (self.request.user, email))

            self.request.session.flash(
                self.request._(
                    "Email ${email_address} added - check your email for "
                    "a verification link",
                    mapping={"email_address": email.email},
                ),
                queue="success",
            )
            return self.default_response

        return {**self.default_response, "add_email_form": form}

    @view_config(
        request_method="POST", request_param=["delete_email_id"], require_reauth=True
    )
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
            self.user_service.record_event(
                self.request.user.id,
                tag="account:email:remove",
                ip_address=self.request.remote_addr,
                additional={"email": email.email},
            )
            self.request.session.flash(
                f"Email address {email.email} removed", queue="success"
            )
        return self.default_response

    @view_config(
        request_method="POST", request_param=["primary_email_id"], require_reauth=True
    )
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
        self.user_service.record_event(
            self.request.user.id,
            tag="account:email:primary:change",
            ip_address=self.request.remote_addr,
            additional={
                "old_primary": previous_primary_email.email
                if previous_primary_email
                else None,
                "new_primary": new_primary_email.email,
            },
        )

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
            email.user.record_event(
                tag="account:email:reverify",
                ip_address=self.request.remote_addr,
                additional={"email": email.email},
            )

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
            self.user_service.record_event(
                self.request.user.id,
                tag="account:password:change",
                ip_address=self.request.remote_addr,
            )
            send_password_change_email(self.request, self.request.user)
            self.request.session.flash("Password updated", queue="success")

        return {**self.default_response, "change_password_form": form}

    @view_config(
        request_method="POST", request_param=DeleteTOTPForm.__params__
    )  # TODO: gate_action instead of confirm pass form
    def delete_account(self):
        confirm_password = self.request.params.get("confirm_password")
        if not confirm_password:
            self.request.session.flash("Confirm the request", queue="error")
            return self.default_response

        form = ConfirmPasswordForm(
            password=confirm_password,
            username=self.request.user.username,
            user_service=self.user_service,
        )

        if not form.validate():
            self.request.session.flash(
                "Could not delete account - Invalid credentials. Please try again.",
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
    has_translations=True,
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
        if not self.request.user.has_primary_verified_email:
            self.request.session.flash(
                "Verify your email to modify two factor authentication", queue="error"
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
        if not self.request.user.has_primary_verified_email:
            self.request.session.flash(
                "Verify your email to modify two factor authentication", queue="error"
            )
            return Response(status=403)

        totp_secret = self.user_service.get_totp_secret(self.request.user.id)
        if totp_secret:
            self.request.session.flash(
                "Account cannot be linked to more than one authentication "
                "application at a time",
                queue="error",
            )
            return HTTPSeeOther(self.request.route_path("manage.account"))

        return self.default_response

    @view_config(request_method="POST", request_param=ProvisionTOTPForm.__params__)
    def validate_totp_provision(self):
        if not self.request.user.has_primary_verified_email:
            self.request.session.flash(
                "Verify your email to modify two factor authentication", queue="error"
            )
            return Response(status=403)

        totp_secret = self.user_service.get_totp_secret(self.request.user.id)
        if totp_secret:
            self.request.session.flash(
                "Account cannot be linked to more than one authentication "
                "application at a time",
                queue="error",
            )
            return HTTPSeeOther(self.request.route_path("manage.account"))

        form = ProvisionTOTPForm(
            **self.request.POST, totp_secret=self.request.session.get_totp_secret()
        )

        if form.validate():
            self.user_service.update_user(
                self.request.user.id, totp_secret=self.request.session.get_totp_secret()
            )
            self.request.session.clear_totp_secret()
            self.user_service.record_event(
                self.request.user.id,
                tag="account:two_factor:method_added",
                ip_address=self.request.remote_addr,
                additional={"method": "totp"},
            )
            self.request.session.flash(
                "Authentication application successfully set up", queue="success"
            )
            send_two_factor_added_email(self.request, self.request.user, method="totp")

            return HTTPSeeOther(self.request.route_path("manage.account"))

        return {**self.default_response, "provision_totp_form": form}

    @view_config(request_method="POST", request_param=DeleteTOTPForm.__params__)
    def delete_totp(self):
        if not self.request.user.has_primary_verified_email:
            self.request.session.flash(
                "Verify your email to modify two factor authentication", queue="error"
            )
            return Response(status=403)

        totp_secret = self.user_service.get_totp_secret(self.request.user.id)
        if not totp_secret:
            self.request.session.flash(
                "There is no authentication application to delete", queue="error"
            )
            return HTTPSeeOther(self.request.route_path("manage.account"))

        form = DeleteTOTPForm(
            password=self.request.POST["confirm_password"],
            username=self.request.user.username,
            user_service=self.user_service,
        )

        if form.validate():
            self.user_service.update_user(self.request.user.id, totp_secret=None)
            self.user_service.record_event(
                self.request.user.id,
                tag="account:two_factor:method_removed",
                ip_address=self.request.remote_addr,
                additional={"method": "totp"},
            )
            self.request.session.flash(
                "Authentication application removed from PyPI. "
                "Remember to remove PyPI from your application.",
                queue="success",
            )
            send_two_factor_removed_email(
                self.request, self.request.user, method="totp"
            )
        else:
            self.request.session.flash("Invalid credentials. Try again", queue="error")

        return HTTPSeeOther(self.request.route_path("manage.account"))


@view_defaults(
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    permission="manage:user",
    http_cache=0,
    has_translations=True,
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
            self.user_service.record_event(
                self.request.user.id,
                tag="account:two_factor:method_added",
                ip_address=self.request.remote_addr,
                additional={"method": "webauthn", "label": form.label.data},
            )
            self.request.session.flash(
                "Security device successfully set up", queue="success"
            )
            send_two_factor_added_email(
                self.request, self.request.user, method="webauthn"
            )

            return {"success": "Security device successfully set up"}

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
            self.request.session.flash(
                "There is no security device to delete", queue="error"
            )
            return HTTPSeeOther(self.request.route_path("manage.account"))

        form = DeleteWebAuthnForm(
            **self.request.POST,
            username=self.request.user.username,
            user_service=self.user_service,
            user_id=self.request.user.id,
        )

        if form.validate():
            self.request.user.webauthn.remove(form.webauthn)
            self.user_service.record_event(
                self.request.user.id,
                tag="account:two_factor:method_removed",
                ip_address=self.request.remote_addr,
                additional={"method": "webauthn", "label": form.label.data},
            )
            self.request.session.flash("Security device removed", queue="success")
            send_two_factor_removed_email(
                self.request, self.request.user, method="webauthn"
            )
        else:
            self.request.session.flash("Invalid credentials", queue="error")

        return HTTPSeeOther(self.request.route_path("manage.account"))


@view_defaults(
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    permission="manage:user",
    http_cache=0,
    has_translations=True,
)
class ProvisionRecoveryCodesViews:
    def __init__(self, request):
        self.request = request
        self.user_service = request.find_service(IUserService, context=None)

    @view_config(
        request_method="GET",
        route_name="manage.account.recovery-codes.generate",
        renderer="manage/account/recovery_codes-provision.html",
    )
    def recovery_codes_generate(self):
        if not self.user_service.has_two_factor(self.request.user.id):
            self.request.session.flash(
                self.request._(
                    "You must provision a two factor method before recovery "
                    "codes can be generated"
                ),
                queue="error",
            )
            return HTTPSeeOther(self.request.route_path("manage.account"))

        if self.user_service.has_recovery_codes(self.request.user.id):
            return {
                "recovery_codes": None,
                "_error": self.request._("Recovery codes already generated"),
                "_message": self.request._(
                    "Generating new recovery codes will invalidate your existing codes."
                ),
            }

        self.user_service.record_event(
            self.request.user.id,
            tag="account:recovery_codes:generated",
            ip_address=self.request.remote_addr,
        )
        return {
            "recovery_codes": self.user_service.generate_recovery_codes(
                self.request.user.id
            )
        }

    @view_config(
        request_method="POST",
        route_name="manage.account.recovery-codes.regenerate",
        renderer="manage/account/recovery_codes-provision.html",
    )
    def recovery_codes_regenerate(self):
        if not self.user_service.has_two_factor(self.request.user.id):
            self.request.session.flash(
                self.request._(
                    "You must provision a two factor method before recovery "
                    "codes can be generated"
                ),
                queue="error",
            )
            return HTTPSeeOther(self.request.route_path("manage.account"))

        form = ConfirmPasswordForm(
            password=self.request.POST["confirm_password"],
            username=self.request.user.username,
            user_service=self.user_service,
        )

        if form.validate():
            self.user_service.record_event(
                self.request.user.id,
                tag="account:recovery_codes:regenerated",
                ip_address=self.request.remote_addr,
            )
            return {
                "recovery_codes": self.user_service.generate_recovery_codes(
                    self.request.user.id
                )
            }

        self.request.session.flash(
            self.request._("Invalid credentials. Try again"), queue="error"
        )
        return HTTPSeeOther(self.request.route_path("manage.account"))


@view_defaults(
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    permission="manage:user",
    renderer="manage/token.html",
    route_name="manage.account.token",
    has_translations=True,
    require_reauth=True,
)
class ProvisionMacaroonViews:
    def __init__(self, request):
        self.request = request
        self.user_service = request.find_service(IUserService, context=None)
        self.macaroon_service = request.find_service(IMacaroonService, context=None)

    @property
    def project_names(self):
        return sorted(project.normalized_name for project in self.request.user.projects)

    @property
    def default_response(self):
        return {
            "project_names": self.project_names,
            "create_macaroon_form": CreateMacaroonForm(
                user_id=self.request.user.id,
                macaroon_service=self.macaroon_service,
                project_names=self.project_names,
            ),
            "delete_macaroon_form": DeleteMacaroonForm(
                username=self.request.user.username,
                user_service=self.user_service,
                macaroon_service=self.macaroon_service,
            ),
        }

    @view_config(request_method="GET")
    def manage_macaroons(self):
        return self.default_response

    @view_config(request_method="POST", require_reauth=True)
    def create_macaroon(self):
        if not self.request.user.has_primary_verified_email:
            self.request.session.flash(
                "Verify your email to create an API token.", queue="error"
            )
            return HTTPSeeOther(self.request.route_path("manage.account"))

        form = CreateMacaroonForm(
            **self.request.POST,
            user_id=self.request.user.id,
            macaroon_service=self.macaroon_service,
            project_names=self.project_names,
        )

        response = {**self.default_response}
        if form.validate():
            macaroon_caveats = {"permissions": form.validated_scope, "version": 1}
            serialized_macaroon, macaroon = self.macaroon_service.create_macaroon(
                location=self.request.domain,
                user_id=self.request.user.id,
                description=form.description.data,
                caveats=macaroon_caveats,
            )
            self.user_service.record_event(
                self.request.user.id,
                tag="account:api_token:added",
                ip_address=self.request.remote_addr,
                additional={
                    "description": form.description.data,
                    "caveats": macaroon_caveats,
                },
            )
            if "projects" in form.validated_scope:
                projects = [
                    project
                    for project in self.request.user.projects
                    if project.normalized_name in form.validated_scope["projects"]
                ]
                for project in projects:
                    # NOTE: We don't disclose the full caveats for this token
                    # to the project event log, since the token could also
                    # have access to projects that this project's owner
                    # isn't aware of.
                    project.record_event(
                        tag="project:api_token:added",
                        ip_address=self.request.remote_addr,
                        additional={
                            "description": form.description.data,
                            "user": self.request.user.username,
                        },
                    )

            response.update(serialized_macaroon=serialized_macaroon, macaroon=macaroon)

        return {**response, "create_macaroon_form": form}

    @view_config(
        request_method="POST",
        request_param=DeleteMacaroonForm.__params__,
        require_reauth=True,
    )
    def delete_macaroon(self):
        form = DeleteMacaroonForm(
            password=self.request.POST["confirm_password"],
            macaroon_id=self.request.POST["macaroon_id"],
            macaroon_service=self.macaroon_service,
            username=self.request.user.username,
            user_service=self.user_service,
        )

        if form.validate():
            macaroon = self.macaroon_service.find_macaroon(form.macaroon_id.data)
            self.macaroon_service.delete_macaroon(form.macaroon_id.data)
            self.user_service.record_event(
                self.request.user.id,
                tag="account:api_token:removed",
                ip_address=self.request.remote_addr,
                additional={"macaroon_id": form.macaroon_id.data},
            )
            if "projects" in macaroon.caveats["permissions"]:
                projects = [
                    project
                    for project in self.request.user.projects
                    if project.normalized_name
                    in macaroon.caveats["permissions"]["projects"]
                ]
                for project in projects:
                    project.record_event(
                        tag="project:api_token:removed",
                        ip_address=self.request.remote_addr,
                        additional={
                            "description": macaroon.description,
                            "user": self.request.user.username,
                        },
                    )
            self.request.session.flash(
                f"Deleted API token '{macaroon.description}'.", queue="success"
            )
        else:
            self.request.session.flash("Invalid credentials. Try again", queue="error")

        redirect_to = self.request.referer
        if not is_safe_url(redirect_to, host=self.request.host):
            redirect_to = self.request.route_path("manage.account")
        return HTTPSeeOther(redirect_to)


@view_config(
    route_name="manage.projects",
    renderer="manage/projects.html",
    uses_session=True,
    permission="manage:user",
    has_translations=True,
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
    project_invites = (
        request.db.query(RoleInvitation)
        .filter(RoleInvitation.invite_status == RoleInvitationStatus.Pending)
        .filter(RoleInvitation.user == request.user)
        .all()
    )
    project_invites = [
        (role_invite.project, role_invite.token) for role_invite in project_invites
    ]
    return {
        "projects": sorted(request.user.projects, key=_key, reverse=True),
        "projects_owned": projects_owned,
        "projects_sole_owned": projects_sole_owned,
        "project_invites": project_invites,
    }


@view_config(
    route_name="manage.project.settings",
    context=Project,
    renderer="manage/settings.html",
    uses_session=True,
    permission="manage:project",
    has_translations=True,
    require_reauth=True,
)
def manage_project_settings(project, request):
    return {
        "project": project,
        "MAX_FILESIZE": MAX_FILESIZE,
        "MAX_PROJECT_SIZE": MAX_PROJECT_SIZE,
    }


def get_user_role_in_project(project, user, request):
    return (
        request.db.query(Role)
        .filter(Role.user == user, Role.project == project)
        .one()
        .role_name
    )


@view_config(
    route_name="manage.project.delete_project",
    context=Project,
    uses_session=True,
    require_methods=["POST"],
    permission="manage:project",
    has_translations=True,
    require_reauth=True,
)
def delete_project(project, request):
    if request.flags.enabled(AdminFlagValue.DISALLOW_DELETION):
        request.session.flash(
            (
                "Project deletion temporarily disabled. "
                "See https://pypi.org/help#admin-intervention for details."
            ),
            queue="error",
        )
        return HTTPSeeOther(
            request.route_path("manage.project.settings", project_name=project.name)
        )

    confirm_project(project, request, fail_route="manage.project.settings")

    submitter_role = get_user_role_in_project(project, request.user, request)

    for contributor in project.users:
        contributor_role = get_user_role_in_project(project, contributor, request)

        send_removed_project_email(
            request,
            contributor,
            project_name=project.name,
            submitter_name=request.user.username,
            submitter_role=submitter_role,
            recipient_role=contributor_role,
        )

    remove_project(project, request)

    return HTTPSeeOther(request.route_path("manage.projects"))


@view_config(
    route_name="manage.project.destroy_docs",
    context=Project,
    uses_session=True,
    require_methods=["POST"],
    permission="manage:project",
    has_translations=True,
    require_reauth=True,
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
    has_translations=True,
    require_reauth=True,
)
def manage_project_releases(project, request):
    # Get the counts for all the files for this project, grouped by the
    # release version and the package types
    filecounts = (
        request.db.query(Release.version, File.packagetype, func.count(File.id))
        .options(Load(Release).load_only("version"))
        .outerjoin(File)
        .group_by(Release.id)
        .group_by(File.packagetype)
        .filter(Release.project == project)
        .all()
    )

    # Turn rows like:
    #   [('0.1', 'bdist_wheel', 2), ('0.1', 'sdist', 1)]
    # into:
    #   {
    #       '0.1: {
    #            'bdist_wheel': 2,
    #            'sdist': 1,
    #            'total': 3,
    #       }
    #   }

    version_to_file_counts = {}
    for version, packagetype, count in filecounts:
        packagetype_to_count = version_to_file_counts.setdefault(version, {})
        packagetype_to_count.setdefault("total", 0)
        packagetype_to_count[packagetype] = count
        packagetype_to_count["total"] += count

    return {"project": project, "version_to_file_counts": version_to_file_counts}


@view_defaults(
    route_name="manage.project.release",
    context=Release,
    renderer="manage/release.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    permission="manage:project",
    has_translations=True,
    require_reauth=True,
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
        request_param=["confirm_yank_version"],
        require_reauth=True,
    )
    def yank_project_release(self):
        version = self.request.POST.get("confirm_yank_version")
        yanked_reason = self.request.POST.get("yanked_reason", "")

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
                "Could not yank release - "
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

        submitter_role = get_user_role_in_project(
            self.release.project, self.request.user, self.request
        )

        self.request.db.add(
            JournalEntry(
                name=self.release.project.name,
                action="yank release",
                version=self.release.version,
                submitted_by=self.request.user,
                submitted_from=self.request.remote_addr,
            )
        )

        self.release.project.record_event(
            tag="project:release:yank",
            ip_address=self.request.remote_addr,
            additional={
                "submitted_by": self.request.user.username,
                "canonical_version": self.release.canonical_version,
                "yanked_reason": yanked_reason,
            },
        )

        self.release.yanked = True
        self.release.yanked_reason = yanked_reason

        self.request.session.flash(
            f"Yanked release {self.release.version!r}", queue="success"
        )

        for contributor in self.release.project.users:
            contributor_role = get_user_role_in_project(
                self.release.project, contributor, self.request
            )

            send_yanked_project_release_email(
                self.request,
                contributor,
                release=self.release,
                submitter_name=self.request.user.username,
                submitter_role=submitter_role,
                recipient_role=contributor_role,
            )

        return HTTPSeeOther(
            self.request.route_path(
                "manage.project.releases", project_name=self.release.project.name
            )
        )

    @view_config(
        request_method="POST",
        request_param=["confirm_unyank_version"],
        require_reauth=True,
    )
    def unyank_project_release(self):
        version = self.request.POST.get("confirm_unyank_version")
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
                "Could not un-yank release - "
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

        submitter_role = get_user_role_in_project(
            self.release.project, self.request.user, self.request
        )

        self.request.db.add(
            JournalEntry(
                name=self.release.project.name,
                action="unyank release",
                version=self.release.version,
                submitted_by=self.request.user,
                submitted_from=self.request.remote_addr,
            )
        )

        self.release.project.record_event(
            tag="project:release:unyank",
            ip_address=self.request.remote_addr,
            additional={
                "submitted_by": self.request.user.username,
                "canonical_version": self.release.canonical_version,
            },
        )

        self.release.yanked = False
        self.release.yanked_reason = ""

        self.request.session.flash(
            f"Un-yanked release {self.release.version!r}", queue="success"
        )

        for contributor in self.release.project.users:
            contributor_role = get_user_role_in_project(
                self.release.project, contributor, self.request
            )

            send_unyanked_project_release_email(
                self.request,
                contributor,
                release=self.release,
                submitter_name=self.request.user.username,
                submitter_role=submitter_role,
                recipient_role=contributor_role,
            )

        return HTTPSeeOther(
            self.request.route_path(
                "manage.project.releases", project_name=self.release.project.name
            )
        )

    @view_config(
        request_method="POST",
        request_param=["confirm_delete_version"],
        require_reauth=True,
    )
    def delete_project_release(self):
        if self.request.flags.enabled(AdminFlagValue.DISALLOW_DELETION):
            self.request.session.flash(
                (
                    "Project deletion temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )
            return HTTPSeeOther(
                self.request.route_path(
                    "manage.project.release",
                    project_name=self.release.project.name,
                    version=self.release.version,
                )
            )

        version = self.request.POST.get("confirm_delete_version")
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

        submitter_role = get_user_role_in_project(
            self.release.project, self.request.user, self.request
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

        self.release.project.record_event(
            tag="project:release:remove",
            ip_address=self.request.remote_addr,
            additional={
                "submitted_by": self.request.user.username,
                "canonical_version": self.release.canonical_version,
            },
        )

        self.request.db.delete(self.release)

        self.request.session.flash(
            f"Deleted release {self.release.version!r}", queue="success"
        )

        for contributor in self.release.project.users:
            contributor_role = get_user_role_in_project(
                self.release.project, contributor, self.request
            )

            send_removed_project_release_email(
                self.request,
                contributor,
                release=self.release,
                submitter_name=self.request.user.username,
                submitter_role=submitter_role,
                recipient_role=contributor_role,
            )

        return HTTPSeeOther(
            self.request.route_path(
                "manage.project.releases", project_name=self.release.project.name
            )
        )

    @view_config(
        request_method="POST",
        request_param=["confirm_project_name", "file_id"],
        require_reauth=True,
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

        if self.request.flags.enabled(AdminFlagValue.DISALLOW_DELETION):
            message = (
                "Project deletion temporarily disabled. "
                "See https://pypi.org/help#admin-intervention for details."
            )
            return _error(message)

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

        self.release.project.record_event(
            tag="project:release:file:remove",
            ip_address=self.request.remote_addr,
            additional={
                "submitted_by": self.request.user.username,
                "canonical_version": self.release.canonical_version,
                "filename": release_file.filename,
            },
        )

        submitter_role = get_user_role_in_project(
            self.release.project, self.request.user, self.request
        )

        for contributor in self.release.project.users:
            contributor_role = get_user_role_in_project(
                self.release.project, contributor, self.request
            )

            send_removed_project_release_file_email(
                self.request,
                contributor,
                file=release_file.filename,
                release=self.release,
                submitter_name=self.request.user.username,
                submitter_role=submitter_role,
                recipient_role=contributor_role,
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
    has_translations=True,
    require_reauth=True,
)
def manage_project_roles(project, request, _form_class=CreateRoleForm):
    user_service = request.find_service(IUserService, context=None)
    form = _form_class(request.POST, user_service=user_service)

    if request.method == "POST" and form.validate():
        username = form.username.data
        role_name = form.role_name.data
        userid = user_service.find_userid(username)
        user = user_service.get_user(userid)
        token_service = request.find_service(ITokenService, name="email")

        existing_role = (
            request.db.query(Role)
            .filter(Role.user == user, Role.project == project)
            .first()
        )
        user_invite = (
            request.db.query(RoleInvitation)
            .filter(RoleInvitation.user == user)
            .filter(RoleInvitation.project == project)
            .one_or_none()
        )
        # Cover edge case where invite is invalid but task
        # has not updated invite status
        try:
            invite_token = token_service.loads(user_invite.token)
        except (TokenExpired, AttributeError):
            invite_token = None

        if existing_role:
            request.session.flash(
                request._(
                    "User '${username}' already has ${role_name} role for project",
                    mapping={
                        "username": username,
                        "role_name": existing_role.role_name,
                    },
                ),
                queue="error",
            )
        elif user.primary_email is None or not user.primary_email.verified:
            request.session.flash(
                request._(
                    "User '${username}' does not have a verified primary email "
                    "address and cannot be added as a ${role_name} for project",
                    mapping={"username": username, "role_name": role_name},
                ),
                queue="error",
            )
        elif (
            user_invite
            and user_invite.invite_status == RoleInvitationStatus.Pending
            and invite_token
        ):
            request.session.flash(
                request._(
                    "User '${username}' already has an active invite. "
                    "Please try again later.",
                    mapping={"username": username},
                ),
                queue="error",
            )
        else:
            invite_token = token_service.dumps(
                {
                    "action": "email-project-role-verify",
                    "desired_role": role_name,
                    "user_id": user.id,
                    "project_id": project.id,
                    "submitter_id": request.user.id,
                }
            )
            if user_invite:
                user_invite.invite_status = RoleInvitationStatus.Pending
                user_invite.token = invite_token
            else:
                request.db.add(
                    RoleInvitation(
                        user=user,
                        project=project,
                        invite_status=RoleInvitationStatus.Pending,
                        token=invite_token,
                    )
                )

            request.db.add(
                JournalEntry(
                    name=project.name,
                    action=f"invite {role_name} {username}",
                    submitted_by=request.user,
                    submitted_from=request.remote_addr,
                )
            )
            send_project_role_verification_email(
                request,
                user,
                desired_role=role_name,
                initiator_username=request.user.username,
                project_name=project.name,
                email_token=invite_token,
                token_age=token_service.max_age,
            )
            project.record_event(
                tag="project:role:invite",
                ip_address=request.remote_addr,
                additional={
                    "submitted_by": request.user.username,
                    "role_name": role_name,
                    "target_user": username,
                },
            )
            request.db.flush()  # in order to get id
            request.session.flash(
                request._(
                    "Invitation sent to '${username}'",
                    mapping={"username": username},
                ),
                queue="success",
            )

        form = _form_class(user_service=user_service)

    roles = set(request.db.query(Role).join(User).filter(Role.project == project).all())
    invitations = set(
        request.db.query(RoleInvitation)
        .join(User)
        .filter(RoleInvitation.project == project)
        .all()
    )

    return {
        "project": project,
        "roles": roles,
        "invitations": invitations,
        "form": form,
    }


@view_config(
    route_name="manage.project.revoke_invite",
    context=Project,
    uses_session=True,
    require_methods=["POST"],
    permission="manage:project",
    has_translations=True,
)
def revoke_project_role_invitation(project, request, _form_class=ChangeRoleForm):
    user_service = request.find_service(IUserService, context=None)
    token_service = request.find_service(ITokenService, name="email")
    user = user_service.get_user(request.POST["user_id"])

    try:
        user_invite = (
            request.db.query(RoleInvitation)
            .filter(RoleInvitation.project == project)
            .filter(RoleInvitation.user == user)
            .one()
        )
    except NoResultFound:
        request.session.flash(
            request._("Could not find role invitation."), queue="error"
        )
        return HTTPSeeOther(
            request.route_path("manage.project.roles", project_name=project.name)
        )

    request.db.delete(user_invite)

    try:
        token_data = token_service.loads(user_invite.token)
    except TokenExpired:
        request.session.flash(request._("Invitation already expired."), queue="success")
        return HTTPSeeOther(
            request.route_path("manage.project.roles", project_name=project.name)
        )
    role_name = token_data.get("desired_role")

    request.db.add(
        JournalEntry(
            name=project.name,
            action=f"revoke_invite {role_name} {user.username}",
            submitted_by=request.user,
            submitted_from=request.remote_addr,
        )
    )
    project.record_event(
        tag="project:role:revoke_invite",
        ip_address=request.remote_addr,
        additional={
            "submitted_by": request.user.username,
            "role_name": role_name,
            "target_user": user.username,
        },
    )
    request.session.flash(
        request._(
            "Invitation revoked from '${username}'.",
            mapping={"username": user.username},
        ),
        queue="success",
    )

    return HTTPSeeOther(
        request.route_path("manage.project.roles", project_name=project.name)
    )


@view_config(
    route_name="manage.project.change_role",
    context=Project,
    uses_session=True,
    require_methods=["POST"],
    permission="manage:project",
    has_translations=True,
    require_reauth=True,
)
def change_project_role(project, request, _form_class=ChangeRoleForm):
    form = _form_class(request.POST)

    if form.validate():
        role_id = request.POST["role_id"]
        try:
            role = (
                request.db.query(Role)
                .join(User)
                .filter(Role.id == role_id, Role.project == project)
                .one()
            )
            if role.role_name == "Owner" and role.user == request.user:
                request.session.flash("Cannot remove yourself as Owner", queue="error")
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
                project.record_event(
                    tag="project:role:change",
                    ip_address=request.remote_addr,
                    additional={
                        "submitted_by": request.user.username,
                        "role_name": form.role_name.data,
                        "target_user": role.user.username,
                    },
                )

                owner_roles = (
                    request.db.query(Role)
                    .filter(Role.project == project)
                    .filter(Role.role_name == "Owner")
                    .all()
                )
                owner_users = {owner.user for owner in owner_roles}
                # Don't send owner notification email to new user
                # if they are now an owner
                owner_users.discard(role.user)
                send_collaborator_role_changed_email(
                    request,
                    owner_users,
                    user=role.user,
                    submitter=request.user,
                    project_name=project.name,
                    role=role.role_name,
                )

                send_role_changed_as_collaborator_email(
                    request,
                    role.user,
                    submitter=request.user,
                    project_name=project.name,
                    role=role.role_name,
                )

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
    has_translations=True,
    require_reauth=True,
)
def delete_project_role(project, request):
    try:
        role = (
            request.db.query(Role)
            .join(User)
            .filter(Role.id == request.POST["role_id"])
            .one()
        )
        removing_self = role.role_name == "Owner" and role.user == request.user
        if removing_self:
            request.session.flash("Cannot remove yourself as Owner", queue="error")
        else:
            request.db.delete(role)
            request.db.add(
                JournalEntry(
                    name=project.name,
                    action=f"remove {role.role_name} {role.user.username}",
                    submitted_by=request.user,
                    submitted_from=request.remote_addr,
                )
            )
            project.record_event(
                tag="project:role:delete",
                ip_address=request.remote_addr,
                additional={
                    "submitted_by": request.user.username,
                    "role_name": role.role_name,
                    "target_user": role.user.username,
                },
            )

            owner_roles = (
                request.db.query(Role)
                .filter(Role.project == project)
                .filter(Role.role_name == "Owner")
                .all()
            )
            owner_users = {owner.user for owner in owner_roles}
            # Don't send owner notification email to new user
            # if they are now an owner
            owner_users.discard(role.user)
            send_collaborator_removed_email(
                request,
                owner_users,
                user=role.user,
                submitter=request.user,
                project_name=project.name,
            )

            send_removed_as_collaborator_email(
                request, role.user, submitter=request.user, project_name=project.name
            )

            request.session.flash("Removed role", queue="success")
    except NoResultFound:
        request.session.flash("Could not find role", queue="error")

    return HTTPSeeOther(
        request.route_path("manage.project.roles", project_name=project.name)
    )


@view_config(
    route_name="manage.project.history",
    context=Project,
    renderer="manage/history.html",
    uses_session=True,
    permission="manage:project",
    has_translations=True,
)
def manage_project_history(project, request):
    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.")

    events_query = (
        request.db.query(ProjectEvent)
        .join(ProjectEvent.project)
        .filter(ProjectEvent.project_id == project.id)
        .order_by(ProjectEvent.time.desc())
    )

    events = SQLAlchemyORMPage(
        events_query,
        page=page_num,
        items_per_page=25,
        url_maker=paginate_url_factory(request),
    )

    if events.page_count and page_num > events.page_count:
        raise HTTPNotFound

    return {"project": project, "events": events}


@view_config(
    route_name="manage.project.journal",
    context=Project,
    renderer="manage/journal.html",
    uses_session=True,
    permission="manage:project",
    has_translations=True,
)
def manage_project_journal(project, request):
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
    has_translations=True,
)
def manage_project_documentation(project, request):
    return {"project": project}
