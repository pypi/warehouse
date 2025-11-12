# SPDX-License-Identifier: Apache-2.0

import base64
import io
import uuid

import pyqrcode

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPNotFound,
    HTTPOk,
    HTTPSeeOther,
)
from pyramid.view import view_config, view_defaults
from sqlalchemy import func
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import joinedload
from venusian import lift
from webauthn.helpers import bytes_to_base64url
from webob.multidict import MultiDict

import warehouse.utils.otp as otp

from warehouse.accounts.forms import RecoveryCodeAuthenticationForm
from warehouse.accounts.interfaces import (
    IPasswordBreachedService,
    ITokenService,
    IUserService,
    TokenExpired,
)
from warehouse.accounts.models import Email, User
from warehouse.accounts.views import logout
from warehouse.admin.flags import AdminFlagValue
from warehouse.authnz import Permissions
from warehouse.constants import MAX_FILESIZE, MAX_PROJECT_SIZE
from warehouse.email import (
    send_account_deletion_email,
    send_added_as_collaborator_email,
    send_added_as_team_collaborator_email,
    send_collaborator_added_email,
    send_collaborator_removed_email,
    send_collaborator_role_changed_email,
    send_email_verification_email,
    send_new_email_added_email,
    send_password_change_email,
    send_primary_email_change_email,
    send_project_role_verification_email,
    send_recovery_codes_generated_email,
    send_removed_as_collaborator_email,
    send_removed_project_email,
    send_removed_project_release_email,
    send_removed_project_release_file_email,
    send_role_changed_as_collaborator_email,
    send_team_collaborator_added_email,
    send_two_factor_added_email,
    send_two_factor_removed_email,
    send_unyanked_project_release_email,
    send_yanked_project_release_email,
)
from warehouse.events.tags import EventTag
from warehouse.macaroons import caveats
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.manage.forms import (
    AddAlternateRepositoryForm,
    AddEmailForm,
    ChangePasswordForm,
    ChangeRoleForm,
    ConfirmPasswordForm,
    CreateInternalRoleForm,
    CreateMacaroonForm,
    CreateRoleForm,
    DeleteMacaroonForm,
    DeleteTOTPForm,
    DeleteWebAuthnForm,
    ProvisionTOTPForm,
    ProvisionWebAuthnForm,
    SaveAccountForm,
    TransferOrganizationProjectForm,
)
from warehouse.manage.views.organizations import (
    organization_managers,
    organization_members,
    organization_owners,
)
from warehouse.manage.views.view_helpers import (
    project_owners,
    user_organizations,
    user_projects,
)
from warehouse.organizations.interfaces import IOrganizationService
from warehouse.organizations.models import (
    OrganizationProject,
    OrganizationRole,
    OrganizationRoleType,
    Team,
    TeamProjectRole,
    TeamRole,
)
from warehouse.packaging.models import (
    AlternateRepository,
    File,
    JournalEntry,
    Project,
    Release,
    Role,
    RoleInvitation,
    RoleInvitationStatus,
)
from warehouse.rate_limiting import IRateLimiter
from warehouse.utils.http import is_safe_url
from warehouse.utils.paginate import paginate_url_factory
from warehouse.utils.project import (
    archive_project,
    confirm_project,
    destroy_docs,
    remove_project,
    unarchive_project,
)


class ManageAccountMixin:
    def __init__(self, request):
        self.request = request
        self.user_service = request.find_service(IUserService, context=None)
        self.breach_service = request.find_service(
            IPasswordBreachedService, context=None
        )

    @view_config(request_method="POST", request_param=["reverify_email_id"])
    def reverify_email(self):
        try:
            email = (
                self.request.db.query(Email)
                .filter(
                    Email.id == int(self.request.POST["reverify_email_id"]),
                    Email.user_id == self.request.user.id,
                )
                .one()
            )
        except (NoResultFound, ValueError):
            self.request.session.flash("Email address not found", queue="error")
            if self.request.user.has_primary_verified_email:
                return HTTPSeeOther(self.request.route_path("manage.account"))
            else:
                return HTTPSeeOther(
                    self.request.route_path("manage.unverified-account")
                )

        if email.verified:
            self.request.session.flash("Email is already verified", queue="error")
        else:
            verify_email_ratelimit = self.request.find_service(
                IRateLimiter, name="email.verify"
            )
            if verify_email_ratelimit.test(self.request.user.id):
                send_email_verification_email(self.request, (self.request.user, email))
                verify_email_ratelimit.hit(self.request.user.id)
                email.user.record_event(
                    tag=EventTag.Account.EmailReverify,
                    request=self.request,
                    additional={"email": email.email},
                )

                self.request.session.flash(
                    f"Verification email for {email.email} resent", queue="success"
                )
            else:
                self.request.session.flash(
                    (
                        "Too many incomplete attempts to verify email address(es) for "
                        f"{self.request.user.username}. Complete a pending "
                        "verification or wait before attempting again."
                    ),
                    queue="error",
                )

        if self.request.user.has_primary_verified_email:
            return HTTPSeeOther(self.request.route_path("manage.account"))
        else:
            return HTTPSeeOther(self.request.route_path("manage.unverified-account"))

    @view_config(
        request_method="POST", request_param=["primary_email_id"], require_reauth=True
    )
    def change_primary_email(self):
        if not self.request.user.has_two_factor:
            self.request.session.flash(
                "Two factor authentication must be enabled to change primary "
                "email address.",
                queue="error",
            )
            return self.default_response

        previous_primary_email = self.request.user.primary_email
        try:
            new_primary_email = (
                self.request.db.query(Email)
                .filter(
                    Email.user_id == self.request.user.id,
                    Email.id == int(self.request.POST["primary_email_id"]),
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
        self.request.user.record_event(
            tag=EventTag.Account.EmailPrimaryChange,
            request=self.request,
            additional={
                "old_primary": (
                    previous_primary_email.email if previous_primary_email else None
                ),
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

        return HTTPSeeOther(self.request.path)


@view_defaults(
    route_name="manage.unverified-account",
    renderer="warehouse:templates/manage/unverified-account.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    permission=Permissions.AccountManage,
    has_translations=True,
    require_reauth=True,
)
@lift()
class ManageUnverifiedAccountViews(ManageAccountMixin):
    @view_config(request_method="GET")
    def manage_unverified_account(self):
        if self.request.user.has_primary_verified_email:
            return HTTPSeeOther(self.request.route_path("manage.account"))

        return {"help_url": self.request.help_url(_anchor="account-recovery")}


@view_defaults(
    route_name="manage.account",
    renderer="warehouse:templates/manage/account.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    permission=Permissions.AccountManage,
    has_translations=True,
    require_reauth=True,
)
@lift()
class ManageVerifiedAccountViews(ManageAccountMixin):
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
                request=self.request,
                user_service=self.user_service,
                user_id=self.request.user.id,
            ),
            "change_password_form": ChangePasswordForm(
                request=self.request,
                user_service=self.user_service,
                breach_service=self.breach_service,
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
            self.request.session.flash(
                self.request._("Account details updated"), queue="success"
            )
            return HTTPSeeOther(self.request.path)

        return {**self.default_response, "save_account_form": form}

    @view_config(
        request_method="POST",
        request_param=AddEmailForm.__params__,
        require_reauth=True,
    )
    def add_email(self):
        form = AddEmailForm(
            self.request.POST,
            request=self.request,
            user_service=self.user_service,
            user_id=self.request.user.id,
        )

        if form.validate():
            email = self.user_service.add_email(self.request.user.id, form.email.data)
            self.request.user.record_event(
                tag=EventTag.Account.EmailAdd,
                request=self.request,
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

            for previously_registered_email in self.request.user.emails:
                if previously_registered_email != email:
                    send_new_email_added_email(
                        self.request,
                        (self.request.user, previously_registered_email),
                        new_email_address=email.email,
                    )

            return HTTPSeeOther(self.request.path)

        return {**self.default_response, "add_email_form": form}

    @view_config(
        request_method="POST", request_param=["delete_email_id"], require_reauth=True
    )
    def delete_email(self):
        try:
            email = (
                self.request.db.query(Email)
                .filter(
                    Email.id == int(self.request.POST["delete_email_id"]),
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
            self.request.user.record_event(
                tag=EventTag.Account.EmailRemove,
                request=self.request,
                additional={"email": email.email},
            )
            self.request.session.flash(
                f"Email address {email.email} removed", queue="success"
            )
            return HTTPSeeOther(self.request.path)

        return self.default_response

    @view_config(request_method="POST", request_param=ChangePasswordForm.__params__)
    def change_password(self):
        form = ChangePasswordForm(
            self.request.POST,
            request=self.request,
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
            self.request.user.record_event(
                tag=EventTag.Account.PasswordChange,
                request=self.request,
            )
            send_password_change_email(self.request, self.request.user)
            self.request.db.flush()  # ensure password_date is available
            self.request.db.refresh(self.request.user)  # Pickup new password_date
            self.request.session.record_password_timestamp(
                self.user_service.get_password_timestamp(self.request.user.id)
            )
            self.request.session.flash("Password updated", queue="success")
            return HTTPSeeOther(self.request.path)

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
            formdata=MultiDict(
                {
                    "password": confirm_password,
                    "username": self.request.user.username,
                }
            ),
            request=self.request,
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
            .options(joinedload(JournalEntry.submitted_by))
            .filter(JournalEntry.submitted_by == self.request.user)
            .all()
        )

        for journal in journals:
            journal.submitted_by = deleted_user

        # Attempt to flush to identify any integrity errors before sending an email
        self.request.db.flush()

        # Send a notification email
        send_account_deletion_email(self.request, self.request.user)

        # Actually delete the user
        self.request.db.delete(self.request.user)

        return logout(self.request)


@view_config(
    route_name="manage.account.two-factor",
    renderer="warehouse:templates/manage/account/two-factor.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    permission=Permissions.Account2FA,
    has_translations=True,
    require_reauth=True,
)
def manage_two_factor(request):
    return {}


@view_defaults(
    route_name="manage.account.totp-provision",
    renderer="warehouse:templates/manage/account/totp-provision.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    permission=Permissions.Account2FA,
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
            return HTTPSeeOther(self.request.route_path("manage.account"))

        totp_qr = pyqrcode.create(self.default_response["provision_totp_uri"])
        qr_buffer = io.BytesIO()
        totp_qr.svg(qr_buffer, scale=5)

        return HTTPOk(content_type="image/svg+xml", body=qr_buffer.getvalue())

    @view_config(request_method="GET")
    def totp_provision(self):
        if not self.request.user.has_burned_recovery_codes:
            return HTTPSeeOther(
                self.request.route_path("manage.account.recovery-codes.burn")
            )

        if not self.request.user.has_primary_verified_email:
            self.request.session.flash(
                "Verify your email to modify two factor authentication", queue="error"
            )
            return HTTPSeeOther(self.request.route_path("manage.account"))

        # Clear the TOTP secret in the current session (if it exists) so this
        # page will generate a new TOTP secret rather than using the existing
        # secret to render the QR code.
        self.request.session.clear_totp_secret()

        return self.default_response

    @view_config(request_method="POST", request_param=ProvisionTOTPForm.__params__)
    def validate_totp_provision(self):
        if not self.request.user.has_primary_verified_email:
            self.request.session.flash(
                "Verify your email to modify two factor authentication", queue="error"
            )
            return HTTPSeeOther(self.request.route_path("manage.account"))

        form = ProvisionTOTPForm(
            self.request.POST,
            totp_secret=self.request.session.get_totp_secret(),
        )

        if form.validate():
            old_totp_secret = self.user_service.get_totp_secret(self.request.user.id)
            self.user_service.update_user(
                self.request.user.id, totp_secret=self.request.session.get_totp_secret()
            )
            self.request.session.clear_totp_secret()
            if old_totp_secret:
                self.request.user.record_event(
                    tag=EventTag.Account.TwoFactorMethodRemoved,
                    request=self.request,
                    additional={"method": "totp"},
                )
            self.request.user.record_event(
                tag=EventTag.Account.TwoFactorMethodAdded,
                request=self.request,
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
            return HTTPSeeOther(self.request.route_path("manage.account"))

        totp_secret = self.user_service.get_totp_secret(self.request.user.id)
        if not totp_secret:
            self.request.session.flash(
                "There is no authentication application to delete", queue="error"
            )
            return HTTPSeeOther(self.request.route_path("manage.account"))

        if self.request.user.has_single_2fa:
            self.request.session.flash("Cannot remove last 2FA method", queue="error")
            return HTTPSeeOther(self.request.route_path("manage.account"))

        form = DeleteTOTPForm(
            formdata=MultiDict(
                {
                    "password": self.request.POST["confirm_password"],
                    "username": self.request.user.username,
                }
            ),
            request=self.request,
            user_service=self.user_service,
        )

        if form.validate():
            self.user_service.update_user(self.request.user.id, totp_secret=None)
            self.request.user.record_event(
                tag=EventTag.Account.TwoFactorMethodRemoved,
                request=self.request,
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
    permission=Permissions.Account2FA,
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
        renderer="warehouse:templates/manage/account/webauthn-provision.html",
    )
    def webauthn_provision(self):
        if not self.request.user.has_burned_recovery_codes:
            return HTTPSeeOther(
                self.request.route_path("manage.account.recovery-codes.burn")
            )
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
            self.request.POST,
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
                credential_id=bytes_to_base64url(
                    form.validated_credential.credential_id
                ),
                public_key=bytes_to_base64url(
                    form.validated_credential.credential_public_key
                ),
                sign_count=form.validated_credential.sign_count,
            )
            self.request.user.record_event(
                tag=EventTag.Account.TwoFactorMethodAdded,
                request=self.request,
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

        if self.request.user.has_single_2fa:
            self.request.session.flash("Cannot remove last 2FA method", queue="error")
            return HTTPSeeOther(self.request.route_path("manage.account"))

        form = DeleteWebAuthnForm(
            self.request.POST,
            username=self.request.user.username,
            user_service=self.user_service,
            user_id=self.request.user.id,
        )

        if form.validate():
            self.request.user.webauthn.remove(form.webauthn)
            self.request.user.record_event(
                tag=EventTag.Account.TwoFactorMethodRemoved,
                request=self.request,
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
    permission=Permissions.Account2FA,
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
        renderer="warehouse:templates/manage/account/recovery_codes-provision.html",
        require_reauth=10,  # 10 seconds
    )
    def recovery_codes_generate(self):
        if self.user_service.has_recovery_codes(self.request.user.id):
            return {
                "recovery_codes": None,
                "_error": self.request._("Recovery codes already generated"),
                "_message": self.request._(
                    "Generating new recovery codes will invalidate your existing codes."
                ),
            }

        recovery_codes = self.user_service.generate_recovery_codes(self.request.user.id)
        send_recovery_codes_generated_email(self.request, self.request.user)
        self.request.user.record_event(
            tag=EventTag.Account.RecoveryCodesGenerated,
            request=self.request,
        )

        return {"recovery_codes": recovery_codes}

    @view_config(
        request_method="GET",
        route_name="manage.account.recovery-codes.regenerate",
        renderer="warehouse:templates/manage/account/recovery_codes-provision.html",
        require_reauth=10,  # 10 seconds
    )
    def recovery_codes_regenerate(self):
        recovery_codes = self.user_service.generate_recovery_codes(self.request.user.id)
        send_recovery_codes_generated_email(self.request, self.request.user)
        self.request.user.record_event(
            tag=EventTag.Account.RecoveryCodesRegenerated,
            request=self.request,
        )

        return {"recovery_codes": recovery_codes}

    @view_config(
        route_name="manage.account.recovery-codes.burn",
        renderer="warehouse:templates/manage/account/recovery_codes-burn.html",
    )
    def recovery_codes_burn(self, _form_class=RecoveryCodeAuthenticationForm):
        user = self.user_service.get_user(self.request.user.id)

        if not user.has_recovery_codes:
            return HTTPSeeOther(self.request.route_path("manage.account"))
        if user.has_burned_recovery_codes:
            return HTTPSeeOther(self.request.route_path("manage.account.two-factor"))

        form = _form_class(
            self.request.POST,
            request=self.request,
            user_id=user.id,
            user_service=self.user_service,
        )

        if self.request.method == "POST" and form.validate():
            self.request.session.flash(
                self.request._(
                    "Recovery code accepted. The supplied code cannot be used again."
                ),
                queue="success",
            )
            return HTTPSeeOther(self.request.route_path("manage.account.two-factor"))

        return {"form": form}


@view_defaults(
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    permission=Permissions.AccountAPITokens,
    renderer="warehouse:templates/manage/account/token.html",
    route_name="manage.account.token",
    has_translations=True,
    require_reauth=True,
)
class ProvisionMacaroonViews:
    def __init__(self, request):
        self.request = request
        self.user_service = request.find_service(IUserService, context=None)
        self.macaroon_service = request.find_service(IMacaroonService, context=None)
        self.selected_project = None

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
                selected_project=self.selected_project,
            ),
            "delete_macaroon_form": DeleteMacaroonForm(
                request=self.request,
                username=self.request.user.username,
                user_service=self.user_service,
                macaroon_service=self.macaroon_service,
            ),
        }

    @view_config(request_method="GET")
    def manage_macaroons(self):
        self.selected_project = self.request.params.get("selected_project")
        return self.default_response

    @view_config(request_method="POST", require_reauth=True)
    def create_macaroon(self):
        if not self.request.user.has_primary_verified_email:
            self.request.session.flash(
                self.request._("Verify your email to create an API token."),
                queue="error",
            )
            return HTTPSeeOther(self.request.route_path("manage.account"))

        form = CreateMacaroonForm(
            self.request.POST,
            user_id=self.request.user.id,
            macaroon_service=self.macaroon_service,
            project_names=self.project_names,
        )

        response = {**self.default_response}
        if form.validate():
            macaroon_caveats: list[caveats.Caveat]

            if form.validated_scope == "user":
                recorded_caveats = [{"permissions": form.validated_scope, "version": 1}]
                macaroon_caveats = [
                    caveats.RequestUser(user_id=str(self.request.user.id))
                ]
            else:
                project_ids = [
                    str(project.id)
                    for project in self.request.user.projects
                    if project.normalized_name in form.validated_scope["projects"]
                ]
                recorded_caveats = [
                    {"permissions": form.validated_scope, "version": 1},
                    {"project_ids": project_ids},
                ]
                macaroon_caveats = [
                    caveats.ProjectName(
                        normalized_names=form.validated_scope["projects"]
                    ),
                    caveats.ProjectID(project_ids=project_ids),
                ]

            serialized_macaroon, macaroon = self.macaroon_service.create_macaroon(
                location=self.request.domain,
                description=form.description.data,
                scopes=macaroon_caveats,
                user_id=self.request.user.id,
                additional={"made_with_2fa": self.request.user.has_two_factor},
            )
            self.request.user.record_event(
                tag=EventTag.Account.APITokenAdded,
                request=self.request,
                additional={
                    "description": form.description.data,
                    "caveats": recorded_caveats,
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
                        tag=EventTag.Project.APITokenAdded,
                        request=self.request,
                        additional={
                            "description": form.description.data,
                            "user": self.request.user.username,
                        },
                    )

            # This is an exception to our pattern of redirecting POST to GET.
            response.update(serialized_macaroon=serialized_macaroon, macaroon=macaroon)

        return {**response, "create_macaroon_form": form}

    @view_config(
        request_method="POST",
        request_param=DeleteMacaroonForm.__params__,
        require_reauth=True,
    )
    def delete_macaroon(self):
        form = DeleteMacaroonForm(
            formdata=MultiDict(
                {
                    "password": self.request.POST["confirm_password"],
                    "username": self.request.user.username,
                    "macaroon_id": self.request.POST["macaroon_id"],
                }
            ),
            request=self.request,
            macaroon_service=self.macaroon_service,
            user_service=self.user_service,
        )

        if form.validate():
            macaroon = self.macaroon_service.find_macaroon(form.macaroon_id.data)
            if not macaroon:
                # Return early if no macaroon is found
                self.request.session.flash(
                    self.request._("API Token does not exist."), queue="warning"
                )
                return HTTPSeeOther(self.request.route_path("manage.account"))

            self.macaroon_service.delete_macaroon(form.macaroon_id.data)
            self.request.user.record_event(
                tag=EventTag.Account.APITokenRemoved,
                request=self.request,
                additional={"macaroon_id": form.macaroon_id.data},
            )
            if "projects" in macaroon.permissions_caveat:
                projects = [
                    project
                    for project in self.request.user.projects
                    if project.normalized_name
                    in macaroon.permissions_caveat["projects"]
                ]
                for project in projects:
                    project.record_event(
                        tag=EventTag.Project.APITokenRemoved,
                        request=self.request,
                        additional={
                            "description": macaroon.description,
                            "user": self.request.user.username,
                        },
                    )
            self.request.session.flash(
                self.request._(f"Deleted API token '{macaroon.description}'."),
                queue="success",
            )
        else:
            self.request.session.flash(
                self.request._("Invalid credentials. Try again"), queue="error"
            )

        redirect_to = self.request.referer
        if not is_safe_url(redirect_to, host=self.request.host):
            redirect_to = self.request.route_path("manage.account")
        return HTTPSeeOther(redirect_to)


@view_config(
    route_name="manage.projects",
    renderer="warehouse:templates/manage/projects.html",
    uses_session=True,
    permission=Permissions.ProjectsRead,
    has_translations=True,
)
def manage_projects(request):
    def _key(project):
        if project.releases:
            return project.releases[0].created
        return project.created

    projects = set(request.user.projects)

    all_user_projects = user_projects(request)
    projects |= set(all_user_projects["projects_owned"])
    projects_owned = {project.name for project in all_user_projects["projects_owned"]}
    projects_sole_owned = {
        project.name for project in all_user_projects["projects_sole_owned"]
    }

    for team in request.user.teams:
        projects |= set(team.projects)

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
        "projects": sorted(projects, key=_key, reverse=True),
        "projects_owned": projects_owned,
        "projects_sole_owned": projects_sole_owned,
        "project_invites": project_invites,
    }


@view_defaults(
    route_name="manage.project.settings",
    context=Project,
    renderer="warehouse:templates/manage/project/settings.html",
    uses_session=True,
    permission=Permissions.ProjectsRead,
    has_translations=True,
    require_reauth=True,
    require_methods=False,
)
class ManageProjectSettingsViews:
    def __init__(self, project, request):
        self.project = project
        self.request = request
        self.transfer_organization_project_form_class = TransferOrganizationProjectForm
        self.add_alternate_repository_form_class = AddAlternateRepositoryForm

    @view_config(request_method="GET")
    def manage_project_settings(self):
        if not self.request.organization_access:
            # Disable transfer of project to any organization.
            organization_choices = set()
        else:
            # Allow transfer of project to active orgs owned or managed by user.
            all_user_organizations = user_organizations(self.request)
            active_organizations_owned = {
                organization
                for organization in all_user_organizations["organizations_owned"]
                if organization.is_active
            }
            active_organizations_managed = {
                organization
                for organization in all_user_organizations["organizations_managed"]
                if organization.is_active
            }
            current_organization = (
                {self.project.organization} if self.project.organization else set()
            )
            organization_choices = (
                active_organizations_owned | active_organizations_managed
            ) - current_organization

        add_alt_repo_form = self.add_alternate_repository_form_class()

        return {
            "project": self.project,
            "MAX_FILESIZE": MAX_FILESIZE,
            "MAX_PROJECT_SIZE": MAX_PROJECT_SIZE,
            "transfer_organization_project_form": (
                self.transfer_organization_project_form_class(
                    organization_choices=organization_choices,
                )
            ),
            "add_alternate_repository_form_class": add_alt_repo_form,
        }

    @view_config(
        request_method="POST",
        request_param=AddAlternateRepositoryForm.__params__
        + ["alternate_repository_location=add"],
        require_reauth=True,
        permission=Permissions.ProjectsWrite,
    )
    def add_project_alternate_repository(self):
        form = self.add_alternate_repository_form_class(self.request.POST)

        if not form.validate():
            self.request.session.flash(
                self.request._("Invalid alternate repository location details"),
                queue="error",
            )
            return HTTPSeeOther(
                self.request.route_path(
                    "manage.project.settings",
                    project_name=self.project.name,
                )
            )

        # add the alternate repository location entry
        alt_repo = AlternateRepository(
            project=self.project,
            name=form.display_name.data,
            url=form.link_url.data,
            description=form.description.data,
        )
        self.request.db.add(alt_repo)
        self.project.record_event(
            tag=EventTag.Project.AlternateRepositoryAdd,
            request=self.request,
            additional={
                "added_by": self.request.user.username,
                "display_name": alt_repo.name,
                "link_url": alt_repo.url,
            },
        )
        self.request.user.record_event(
            tag=EventTag.Account.AlternateRepositoryAdd,
            request=self.request,
            additional={
                "added_by": self.request.user.username,
                "display_name": alt_repo.name,
                "link_url": alt_repo.url,
            },
        )
        self.request.session.flash(
            self.request._(
                "Added alternate repository '${name}'",
                mapping={"name": alt_repo.name},
            ),
            queue="success",
        )

        return HTTPSeeOther(
            self.request.route_path(
                "manage.project.settings",
                project_name=self.project.name,
            )
        )

    @view_config(
        request_method="POST",
        request_param=[
            "alternate_repository_id",
            "alternate_repository_location=delete",
        ],
        require_reauth=True,
        permission=Permissions.ProjectsWrite,
    )
    def delete_project_alternate_repository(self):
        confirm_name = self.request.POST.get("confirm_alternate_repository_name")
        resp_inst = HTTPSeeOther(
            self.request.route_path(
                "manage.project.settings", project_name=self.project.name
            )
        )

        # Must confirm alt repo name to delete.
        if not confirm_name:
            self.request.session.flash(
                self.request._("Confirm the request"), queue="error"
            )
            return resp_inst

        # Must provide a valid alt repo id.
        alternate_repository_id = self.request.POST.get("alternate_repository_id", "")
        try:
            uuid.UUID(str(alternate_repository_id))
        except ValueError:
            alternate_repository_id = None
        if not alternate_repository_id:
            self.request.session.flash(
                self.request._("Invalid alternate repository id"),
                queue="error",
            )
            return resp_inst

        # The provided alt repo id must be related to this project.
        alt_repo: AlternateRepository = self.request.db.get(
            AlternateRepository, alternate_repository_id
        )
        if not alt_repo or alt_repo not in self.project.alternate_repositories:
            self.request.session.flash(
                self.request._("Invalid alternate repository for project"),
                queue="error",
            )
            return resp_inst

        # The confirmed alt repo name must match the provided alt repo id.
        if confirm_name != alt_repo.name:
            self.request.session.flash(
                self.request._(
                    "Could not delete alternate repository - "
                    "${confirm} is not the same as ${alt_repo_name}",
                    mapping={"confirm": confirm_name, "alt_repo_name": alt_repo.name},
                ),
                queue="error",
            )
            return resp_inst

        # delete the alternate repository location entry
        self.request.db.delete(alt_repo)
        self.project.record_event(
            tag=EventTag.Project.AlternateRepositoryDelete,
            request=self.request,
            additional={
                "deleted_by": self.request.user.username,
                "display_name": alt_repo.name,
                "link_url": alt_repo.url,
            },
        )
        self.request.user.record_event(
            tag=EventTag.Account.AlternateRepositoryDelete,
            request=self.request,
            additional={
                "deleted_by": self.request.user.username,
                "display_name": alt_repo.name,
                "link_url": alt_repo.url,
            },
        )
        self.request.session.flash(
            self.request._(
                "Deleted alternate repository '${name}'",
                mapping={"name": alt_repo.name},
            ),
            queue="success",
        )

        return resp_inst


def get_user_role_in_project(project, user, request):
    try:
        return (
            request.db.query(Role)
            .filter(Role.user == user, Role.project == project)
            .one()
            .role_name
        )
    except NoResultFound:
        # No project role found so check for Organization roles
        return get_user_role_in_organization_project(project, user, request)


def get_user_role_in_organization_project(project, user, request):
    try:
        # If this is an organization project check to see if user is Org Owner
        role_name = (
            request.db.query(OrganizationRole)
            .join(
                OrganizationProject,
                OrganizationProject.organization_id == OrganizationRole.organization_id,
            )
            .filter(
                OrganizationRole.user == user,
                OrganizationProject.project == project,
                OrganizationRole.role_name == OrganizationRoleType.Owner,
            )
            .one()
            .role_name
        )
    except NoResultFound:
        # Last but not least check if this is a Team Project and user has a team role
        role_name = (
            request.db.query(TeamProjectRole)
            .join(TeamRole, TeamRole.team_id == TeamProjectRole.team_id)
            .filter(
                TeamRole.user == user,
                TeamProjectRole.project == project,
            )
            .one()
            .role_name
        )

    return role_name.value


@view_config(
    route_name="manage.project.delete_project",
    context=Project,
    uses_session=True,
    require_methods=["POST"],
    permission=Permissions.ProjectsWrite,
    has_translations=True,
    require_reauth=True,
)
def delete_project(project, request):
    if request.flags.enabled(AdminFlagValue.DISALLOW_DELETION):
        request.session.flash(
            request._(
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

    contributors = project.users
    if project.organization:
        contributors += project.organization.owners

    for contributor in sorted(contributors):
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
    permission=Permissions.ProjectsWrite,
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
    renderer="warehouse:templates/manage/project/releases.html",
    uses_session=True,
    permission=Permissions.ProjectsRead,
    has_translations=True,
    require_reauth=True,
)
def manage_project_releases(project, request):
    # Get the counts for all the files for this project, grouped by the
    # release version and the package types
    filecounts = (
        request.db.query(Release.version, File.packagetype, func.count(File.id))
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

    version_to_file_counts: dict[str, dict[str, int]] = {}
    for version, packagetype, count in filecounts:
        packagetype_to_count = version_to_file_counts.setdefault(version, {})
        packagetype_to_count.setdefault("total", 0)
        packagetype_to_count[packagetype] = count
        packagetype_to_count["total"] += count

    return {"project": project, "version_to_file_counts": version_to_file_counts}


@view_defaults(
    route_name="manage.project.release",
    context=Release,
    renderer="warehouse:templates/manage/project/release.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    permission=Permissions.ProjectsWrite,
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
            self.request.session.flash(
                self.request._("Confirm the request"), queue="error"
            )
            return HTTPSeeOther(
                self.request.route_path(
                    "manage.project.release",
                    project_name=self.release.project.name,
                    version=self.release.version,
                )
            )

        if version != self.release.version:
            self.request.session.flash(
                self.request._(
                    "Could not yank release - "
                    + f"{version!r} is not the same as {self.release.version!r}"
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

        submitter_role = get_user_role_in_project(
            self.release.project, self.request.user, self.request
        )

        self.request.db.add(
            JournalEntry(
                name=self.release.project.name,
                action="yank release",
                version=self.release.version,
                submitted_by=self.request.user,
            )
        )

        self.release.project.record_event(
            tag=EventTag.Project.ReleaseYank,
            request=self.request,
            additional={
                "submitted_by": self.request.user.username,
                "canonical_version": self.release.canonical_version,
                "yanked_reason": yanked_reason,
            },
        )

        self.release.yanked = True
        self.release.yanked_reason = yanked_reason

        self.request.session.flash(
            self.request._(f"Yanked release {self.release.version!r}"), queue="success"
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
            self.request.session.flash(
                self.request._("Confirm the request"), queue="error"
            )
            return HTTPSeeOther(
                self.request.route_path(
                    "manage.project.release",
                    project_name=self.release.project.name,
                    version=self.release.version,
                )
            )

        if version != self.release.version:
            self.request.session.flash(
                self.request._(
                    "Could not un-yank release - "
                    + f"{version!r} is not the same as {self.release.version!r}"
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

        submitter_role = get_user_role_in_project(
            self.release.project, self.request.user, self.request
        )

        self.request.db.add(
            JournalEntry(
                name=self.release.project.name,
                action="unyank release",
                version=self.release.version,
                submitted_by=self.request.user,
            )
        )

        self.release.project.record_event(
            tag=EventTag.Project.ReleaseUnyank,
            request=self.request,
            additional={
                "submitted_by": self.request.user.username,
                "canonical_version": self.release.canonical_version,
            },
        )

        self.release.yanked = False
        self.release.yanked_reason = ""

        self.request.session.flash(
            self.request._(f"Un-yanked release {self.release.version!r}"),
            queue="success",
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
                self.request._(
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
            self.request.session.flash(
                self.request._("Confirm the request"), queue="error"
            )
            return HTTPSeeOther(
                self.request.route_path(
                    "manage.project.release",
                    project_name=self.release.project.name,
                    version=self.release.version,
                )
            )

        if version != self.release.version:
            self.request.session.flash(
                self.request._(
                    "Could not delete release - "
                    + f"{version!r} is not the same as {self.release.version!r}"
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

        submitter_role = get_user_role_in_project(
            self.release.project, self.request.user, self.request
        )

        self.request.db.add(
            JournalEntry(
                name=self.release.project.name,
                action="remove release",
                version=self.release.version,
                submitted_by=self.request.user,
            )
        )

        self.release.project.record_event(
            tag=EventTag.Project.ReleaseRemove,
            request=self.request,
            additional={
                "submitted_by": self.request.user.username,
                "canonical_version": self.release.canonical_version,
            },
        )

        self.request.db.delete(self.release)

        self.request.session.flash(
            self.request._(f"Deleted release {self.release.version!r}"), queue="success"
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
            message = self.request._(
                "Project deletion temporarily disabled. "
                "See https://pypi.org/help#admin-intervention for details."
            )
            return _error(message)

        project_name = self.request.POST.get("confirm_project_name")

        if not project_name:
            return _error(self.request._("Confirm the request"))

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
            return _error(self.request._("Could not find file"))

        if project_name != self.release.project.name:
            return _error(
                self.request._(
                    "Could not delete file - " + f"{project_name!r} is not the same as "
                    f"{self.release.project.name!r}"
                )
            )

        self.request.db.add(
            JournalEntry(
                name=self.release.project.name,
                action=f"remove file {release_file.filename}",
                version=self.release.version,
                submitted_by=self.request.user,
            )
        )

        release_file.record_event(
            tag=EventTag.File.FileRemove,
            request=self.request,
            additional={
                "submitted_by": self.request.user.username,
                "canonical_version": self.release.canonical_version,
                "filename": release_file.filename,
                "project_id": str(self.release.project.id),
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
    renderer="warehouse:templates/manage/project/roles.html",
    uses_session=True,
    require_methods=False,
    permission=Permissions.ProjectsWrite,
    has_translations=True,
    require_reauth=True,
)
def manage_project_roles(project, request, _form_class=CreateRoleForm):
    organization_service = request.find_service(IOrganizationService, context=None)
    user_service = request.find_service(IUserService, context=None)

    # Roles, invitations, and invite collaborator form for all projects.
    roles = set(request.db.query(Role).join(User).filter(Role.project == project).all())
    invitations = set(
        request.db.query(RoleInvitation)
        .join(User)
        .filter(RoleInvitation.project == project)
        .all()
    )
    form = _form_class(request.POST, user_service=user_service)

    # Team project roles and add internal collaborator form for organization projects.
    enable_internal_collaborator = bool(
        request.organization_access and project.organization
    )
    if enable_internal_collaborator:
        team_project_roles = set(
            request.db.query(TeamProjectRole)
            .join(Team)
            .filter(TeamProjectRole.project == project)
            .all()
        )
        internal_users = set(
            organization_owners(request, project.organization)
            + organization_managers(request, project.organization)
            + organization_members(request, project.organization)
        )
        internal_role_form = CreateInternalRoleForm(
            request.POST,
            team_choices=sorted(team.name for team in project.organization.teams),
            user_choices=sorted(
                user.username for user in internal_users if user not in project.users
            ),
            user_service=user_service,
        )
    else:
        team_project_roles = set()
        internal_role_form = None
        internal_users = set()

    default_response = {
        "project": project,
        "roles": roles,
        "invitations": invitations,
        "form": form,
        "enable_internal_collaborator": enable_internal_collaborator,
        "team_project_roles": team_project_roles,
        "internal_role_form": internal_role_form,
    }

    # Handle GET.
    if request.method != "POST":
        return default_response

    # Determine which form was submitted with POST.
    if enable_internal_collaborator and "is_team" in request.POST:
        form = internal_role_form

    # Validate form.
    if not form.validate():
        return default_response

    # Try adding team as collaborator.
    if enable_internal_collaborator and "is_team" in request.POST and form.is_team.data:
        team_name = form.team_name.data
        role_name = form.team_project_role_name.data
        team_id = organization_service.find_teamid(project.organization.id, team_name)
        team = organization_service.get_team(team_id)

        # Do nothing if role already exists.
        existing_role = (
            request.db.query(TeamProjectRole)
            .filter(TeamProjectRole.team == team, TeamProjectRole.project == project)
            .first()
        )
        if existing_role:
            request.session.flash(
                request._(
                    "Team '${team_name}' already has ${role_name} role for project",
                    mapping={
                        "team_name": team_name,
                        "role_name": existing_role.role_name.value,
                    },
                ),
                queue="error",
            )
            return default_response

        # Add internal team.
        organization_service.add_team_project_role(team.id, project.id, role_name)

        # Add journal entry.
        request.db.add(
            JournalEntry(
                name=project.name,
                action=f"add {role_name.value} {team_name}",
                submitted_by=request.user,
            )
        )

        # Record events.
        project.record_event(
            tag=EventTag.Project.TeamProjectRoleAdd,
            request=request,
            additional={
                "submitted_by_user_id": str(request.user.id),
                "role_name": role_name.value,
                "target_team": team.name,
            },
        )
        team.organization.record_event(
            tag=EventTag.Organization.TeamProjectRoleAdd,
            request=request,
            additional={
                "submitted_by_user_id": str(request.user.id),
                "project_name": project.name,
                "role_name": role_name.value,
                "target_team": team.name,
            },
        )
        team.record_event(
            tag=EventTag.Team.TeamProjectRoleAdd,
            request=request,
            additional={
                "submitted_by_user_id": str(request.user.id),
                "project_name": project.name,
                "role_name": role_name.value,
            },
        )

        # Send notification emails.
        member_users = set(team.members)
        owner_users = set(project.owners + project.organization.owners)
        owner_users -= member_users
        send_team_collaborator_added_email(
            request,
            owner_users,
            team=team,
            submitter=request.user,
            project_name=project.name,
            role=role_name.value,
        )
        send_added_as_team_collaborator_email(
            request,
            member_users,
            team=team,
            submitter=request.user,
            project_name=project.name,
            role=role_name.value,
        )

        # Display notification message.
        request.session.flash(
            request._(
                (
                    "${team_name} now has ${role} permissions "
                    "for the '${project_name}' project."
                ),
                mapping={
                    "team_name": team.name,
                    "project_name": project.name,
                    "role": role_name.value,
                },
            ),
            queue="success",
        )

        # Refresh project collaborators.
        return HTTPSeeOther(request.path)

    # Try adding user as collaborator.
    username = form.username.data
    role_name = form.role_name.data
    userid = user_service.find_userid(username)
    user = user_service.get_user(userid)

    # Do nothing if role already exists.
    existing_role = (
        request.db.query(Role)
        .filter(Role.user == user, Role.project == project)
        .first()
    )
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

        # Refresh project collaborators.
        return HTTPSeeOther(request.path)

    if enable_internal_collaborator and user in internal_users:
        # Add internal member.
        request.db.add(Role(user=user, project=project, role_name=role_name))

        # Add journal entry.
        request.db.add(
            JournalEntry(
                name=project.name,
                action=f"add {role_name} {user.username}",
                submitted_by=request.user,
            )
        )

        # Record events.
        project.record_event(
            tag=EventTag.Project.RoleAdd,
            request=request,
            additional={
                "submitted_by": request.user.username,
                "role_name": role_name,
                "target_user": user.username,
            },
        )
        user.record_event(
            tag=EventTag.Account.RoleAdd,
            request=request,
            additional={
                "submitted_by": request.user.username,
                "project_name": project.name,
                "role_name": role_name,
            },
        )

        # Send notification emails.
        owner_users = set(project.owners + project.organization.owners)
        owner_users.discard(user)
        send_collaborator_added_email(
            request,
            owner_users,
            user=user,
            submitter=request.user,
            project_name=project.name,
            role=role_name,
        )
        send_added_as_collaborator_email(
            request,
            user,
            submitter=request.user,
            project_name=project.name,
            role=role_name,
        )

        # Display notification message.
        request.session.flash(
            request._(
                "${username} is now ${role} of the '${project_name}' project.",
                mapping={
                    "username": username,
                    "project_name": project.name,
                    "role": role_name,
                },
            ),
            queue="success",
        )

        # Refresh project collaborators.
        return HTTPSeeOther(request.path)
    else:
        # Invite external user.
        token_service = request.find_service(ITokenService, name="email")

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

        if user.primary_email is None or not user.primary_email.verified:
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
                tag=EventTag.Project.RoleInvite,
                request=request,
                additional={
                    "submitted_by": request.user.username,
                    "role_name": role_name,
                    "target_user": username,
                },
            )
            user.record_event(
                tag=EventTag.Account.RoleInvite,
                request=request,
                additional={
                    "submitted_by": request.user.username,
                    "project_name": project.name,
                    "role_name": role_name,
                },
            )
            request.session.flash(
                request._(
                    "Invitation sent to '${username}'",
                    mapping={"username": username},
                ),
                queue="success",
            )

        # Refresh project collaborators.
        return HTTPSeeOther(request.path)


@view_config(
    route_name="manage.project.revoke_invite",
    context=Project,
    uses_session=True,
    require_methods=["POST"],
    permission=Permissions.ProjectsWrite,
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
        )
    )
    project.record_event(
        tag=EventTag.Project.RoleRevokeInvite,
        request=request,
        additional={
            "submitted_by": request.user.username,
            "role_name": role_name,
            "target_user": user.username,
        },
    )
    user.record_event(
        tag=EventTag.Account.RoleRevokeInvite,
        request=request,
        additional={
            "submitted_by": request.user.username,
            "project_name": project.name,
            "role_name": role_name,
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
    permission=Permissions.ProjectsWrite,
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
                    )
                )
                role.role_name = form.role_name.data
                project.record_event(
                    tag=EventTag.Project.RoleChange,
                    request=request,
                    additional={
                        "submitted_by": request.user.username,
                        "role_name": form.role_name.data,
                        "target_user": role.user.username,
                    },
                )
                role.user.record_event(
                    tag=EventTag.Account.RoleChange,
                    request=request,
                    additional={
                        "submitted_by": request.user.username,
                        "project_name": project.name,
                        "role_name": form.role_name.data,
                    },
                )

                owner_users = set(project_owners(request, project))
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
    permission=Permissions.ProjectsWrite,
    has_translations=True,
    require_reauth=True,
)
def delete_project_role(project, request):
    try:
        role = (
            request.db.query(Role)
            .join(User)
            .filter(Role.project == project)
            .filter(Role.id == request.POST["role_id"])
            .one()
        )
        projects_sole_owned = {
            project.name for project in user_projects(request)["projects_sole_owned"]
        }
        removing_self = role.role_name == "Owner" and role.user == request.user
        is_sole_owner = project.name in projects_sole_owned
        if removing_self and is_sole_owner:
            request.session.flash("Cannot remove yourself as Sole Owner", queue="error")
        else:
            request.db.delete(role)
            request.db.add(
                JournalEntry(
                    name=project.name,
                    action=f"remove {role.role_name} {role.user.username}",
                    submitted_by=request.user,
                )
            )
            project.record_event(
                tag=EventTag.Project.RoleRemove,
                request=request,
                additional={
                    "submitted_by": request.user.username,
                    "role_name": role.role_name,
                    "target_user": role.user.username,
                },
            )

            owner_users = set(project_owners(request, project))
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

            request.session.flash("Removed collaborator", queue="success")
            if removing_self:
                return HTTPSeeOther(request.route_path("manage.projects"))
    except NoResultFound:
        request.session.flash("Could not find role", queue="error")

    return HTTPSeeOther(
        request.route_path("manage.project.roles", project_name=project.name)
    )


@view_config(
    route_name="manage.project.history",
    context=Project,
    renderer="warehouse:templates/manage/project/history.html",
    uses_session=True,
    permission=Permissions.ProjectsRead,
    has_translations=True,
)
def manage_project_history(project, request):
    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.")

    project_events_query = (
        request.db.query(Project.Event)
        .join(Project.Event.source)
        .filter(Project.Event.source_id == project.id)
    )

    file_events_query = (
        request.db.query(File.Event)
        .join(File.Event.source)
        .filter(File.Event.additional["project_id"].astext == str(project.id))
    )

    events_query = project_events_query.union(file_events_query).order_by(
        Project.Event.time.desc(), File.Event.time.desc()
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
        "project": project,
    }


@view_config(
    route_name="manage.project.documentation",
    context=Project,
    renderer="warehouse:templates/manage/project/documentation.html",
    uses_session=True,
    permission=Permissions.ProjectsRead,
    has_translations=True,
)
def manage_project_documentation(project, request):
    return {"project": project}


@view_config(
    route_name="manage.project.archive",
    context=Project,
    uses_session=True,
    require_methods=["POST"],
    permission=Permissions.ProjectsWrite,
)
def archive_project_view(project, request) -> HTTPSeeOther:
    """
    Archive a Project. Reversible action.
    """
    archive_project(project, request)
    return HTTPSeeOther(
        request.route_path("manage.project.settings", project_name=project.name)
    )


@view_config(
    route_name="manage.project.unarchive",
    context=Project,
    uses_session=True,
    require_methods=["POST"],
    permission=Permissions.ProjectsWrite,
)
def unarchive_project_view(project, request) -> HTTPSeeOther:
    """
    Unarchive a Project. Reversible action.
    """
    unarchive_project(project, request)
    return HTTPSeeOther(
        request.route_path("manage.project.settings", project_name=project.name)
    )
