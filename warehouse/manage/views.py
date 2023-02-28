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

from urllib.parse import urljoin

import pyqrcode

from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPException,
    HTTPNotFound,
    HTTPSeeOther,
    HTTPTooManyRequests,
)
from pyramid.response import Response
from pyramid.view import view_config, view_defaults
from sqlalchemy import func
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Load, joinedload
from webauthn.helpers import bytes_to_base64url

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
from warehouse.email import (
    send_account_deletion_email,
    send_added_as_collaborator_email,
    send_added_as_team_collaborator_email,
    send_added_as_team_member_email,
    send_admin_new_organization_requested_email,
    send_admin_organization_deleted_email,
    send_admin_organization_renamed_email,
    send_canceled_as_invited_organization_member_email,
    send_collaborator_added_email,
    send_collaborator_removed_email,
    send_collaborator_role_changed_email,
    send_email_verification_email,
    send_new_organization_requested_email,
    send_oidc_publisher_added_email,
    send_oidc_publisher_removed_email,
    send_organization_deleted_email,
    send_organization_member_invite_canceled_email,
    send_organization_member_invited_email,
    send_organization_member_removed_email,
    send_organization_member_role_changed_email,
    send_organization_project_added_email,
    send_organization_project_removed_email,
    send_organization_renamed_email,
    send_organization_role_verification_email,
    send_organization_updated_email,
    send_password_change_email,
    send_primary_email_change_email,
    send_project_role_verification_email,
    send_recovery_codes_generated_email,
    send_removed_as_collaborator_email,
    send_removed_as_organization_member_email,
    send_removed_as_team_collaborator_email,
    send_removed_as_team_member_email,
    send_removed_project_email,
    send_removed_project_release_email,
    send_removed_project_release_file_email,
    send_role_changed_as_collaborator_email,
    send_role_changed_as_organization_member_email,
    send_role_changed_as_team_collaborator_email,
    send_team_collaborator_added_email,
    send_team_collaborator_removed_email,
    send_team_collaborator_role_changed_email,
    send_team_created_email,
    send_team_deleted_email,
    send_team_member_added_email,
    send_team_member_removed_email,
    send_two_factor_added_email,
    send_two_factor_removed_email,
    send_unyanked_project_release_email,
    send_yanked_project_release_email,
)
from warehouse.events.tags import EventTag
from warehouse.forklift.legacy import MAX_FILESIZE, MAX_PROJECT_SIZE
from warehouse.macaroons import caveats
from warehouse.macaroons.interfaces import IMacaroonService
from warehouse.manage.forms import (
    AddEmailForm,
    AddOrganizationProjectForm,
    ChangeOrganizationRoleForm,
    ChangePasswordForm,
    ChangeRoleForm,
    ChangeTeamProjectRoleForm,
    ConfirmPasswordForm,
    CreateInternalRoleForm,
    CreateMacaroonForm,
    CreateOrganizationForm,
    CreateOrganizationRoleForm,
    CreateRoleForm,
    CreateTeamForm,
    CreateTeamRoleForm,
    DeleteMacaroonForm,
    DeleteTOTPForm,
    DeleteWebAuthnForm,
    ProvisionTOTPForm,
    ProvisionWebAuthnForm,
    SaveAccountForm,
    SaveOrganizationForm,
    SaveOrganizationNameForm,
    SaveTeamForm,
    Toggle2FARequirementForm,
    TransferOrganizationProjectForm,
)
from warehouse.metrics.interfaces import IMetricsService
from warehouse.oidc.forms import DeletePublisherForm, GitHubPublisherForm
from warehouse.oidc.interfaces import TooManyOIDCRegistrations
from warehouse.oidc.models import GitHubPublisher, OIDCPublisher
from warehouse.organizations.interfaces import IOrganizationService
from warehouse.organizations.models import (
    Organization,
    OrganizationInvitationStatus,
    OrganizationProject,
    OrganizationRole,
    OrganizationRoleType,
    OrganizationType,
    Team,
    TeamProjectRole,
    TeamProjectRoleType,
    TeamRole,
    TeamRoleType,
)
from warehouse.packaging.interfaces import IProjectService
from warehouse.packaging.models import (
    File,
    JournalEntry,
    Project,
    ProjectFactory,
    Release,
    Role,
    RoleInvitation,
    RoleInvitationStatus,
)
from warehouse.rate_limiting import IRateLimiter
from warehouse.subscriptions.interfaces import IBillingService, ISubscriptionService
from warehouse.subscriptions.services import MockStripeBillingService
from warehouse.utils.http import is_safe_url
from warehouse.utils.organization import confirm_organization, confirm_team
from warehouse.utils.paginate import paginate_url_factory
from warehouse.utils.project import (
    confirm_project,
    destroy_docs,
    remove_project,
    validate_project_name,
)


def user_projects(request):
    """Return all the projects for which the user is a sole owner"""
    projects_owned = (
        request.db.query(Project.id.label("id"))
        .join(Role.project)
        .filter(Role.role_name == "Owner", Role.user == request.user)
    )

    projects_collaborator = (
        request.db.query(Project.id)
        .join(Role.project)
        .filter(Role.user == request.user)
    )

    with_sole_owner = (
        # Select projects having just one owner.
        request.db.query(Role.project_id)
        .join(projects_owned.subquery())
        .filter(Role.role_name == "Owner")
        .group_by(Role.project_id)
        .having(func.count(Role.project_id) == 1)
        # Except projects owned by an organization.
        .join(Role.project)
        .filter(~Project.organization.has())
    )

    if not request.flags.enabled(AdminFlagValue.DISABLE_ORGANIZATIONS):
        organizations_owned = (
            request.db.query(Organization.id)
            .join(OrganizationRole.organization)
            .filter(
                OrganizationRole.role_name == OrganizationRoleType.Owner,
                OrganizationRole.user == request.user,
            )
            .subquery()
        )

        organizations_with_sole_owner = (
            request.db.query(OrganizationRole.organization_id)
            .join(organizations_owned)
            .filter(OrganizationRole.role_name == "Owner")
            .group_by(OrganizationRole.organization_id)
            .having(func.count(OrganizationRole.organization_id) == 1)
            .subquery()
        )

        teams = (
            request.db.query(Team.id)
            .join(TeamRole.team)
            .filter(TeamRole.user == request.user)
            .subquery()
        )

        projects_owned = projects_owned.union(
            request.db.query(Project.id.label("id"))
            .join(Organization.projects)
            .join(organizations_owned, Organization.id == organizations_owned.c.id),
            request.db.query(Project.id.label("id"))
            .join(TeamProjectRole.project)
            .join(teams, TeamProjectRole.team_id == teams.c.id)
            .filter(TeamProjectRole.role_name == TeamProjectRoleType.Owner),
        )

        with_sole_owner = with_sole_owner.union(
            # Select projects where organization has only one owner.
            request.db.query(Project.id)
            .join(Organization.projects)
            .join(
                organizations_with_sole_owner,
                Organization.id == organizations_with_sole_owner.c.organization_id,
            )
            # Except projects with any other individual owners.
            .filter(
                ~Project.roles.any(
                    (Role.role_name == "Owner") & (Role.user_id != request.user.id)
                )
            )
        )

    projects_owned = projects_owned.subquery()
    projects_collaborator = projects_collaborator.subquery()
    with_sole_owner = with_sole_owner.subquery()

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
        "projects_requiring_2fa": (
            request.db.query(Project)
            .join(projects_collaborator, Project.id == projects_collaborator.c.id)
            .filter(Project.two_factor_required)
            .order_by(Project.name)
            .all()
        ),
    }


def project_owners(request, project):
    """Return all users who are owners of the project."""
    return project.owners


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
            self.request.session.flash("Account details updated", queue="success")
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
            user_service=self.user_service,
            user_id=self.request.user.id,
        )

        if form.validate():
            email = self.user_service.add_email(self.request.user.id, form.email.data)
            self.user_service.record_event(
                self.request.user.id,
                tag=EventTag.Account.EmailAdd,
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
                tag=EventTag.Account.EmailRemove,
                additional={"email": email.email},
            )
            self.request.session.flash(
                f"Email address {email.email} removed", queue="success"
            )
            return HTTPSeeOther(self.request.path)

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
            tag=EventTag.Account.EmailPrimaryChange,
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

        return HTTPSeeOther(self.request.path)

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
            verify_email_ratelimit = self.request.find_service(
                IRateLimiter, name="email.verify"
            )
            if verify_email_ratelimit.test(self.request.user.id):
                send_email_verification_email(self.request, (self.request.user, email))
                verify_email_ratelimit.hit(self.request.user.id)
                email.user.record_event(
                    tag=EventTag.Account.EmailReverify,
                    ip_address=self.request.remote_addr,
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

        return HTTPSeeOther(self.request.path)

    @view_config(request_method="POST", request_param=ChangePasswordForm.__params__)
    def change_password(self):
        form = ChangePasswordForm(
            **self.request.POST,
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
            self.user_service.record_event(
                self.request.user.id,
                tag=EventTag.Account.PasswordChange,
            )
            send_password_change_email(self.request, self.request.user)
            self.request.db.flush()  # Ensure changes are persisted to DB
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
            request=self.request,
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


@view_config(
    route_name="manage.account.two-factor",
    renderer="manage/account/two-factor.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    permission="manage:user",
    has_translations=True,
    require_reauth=True,
)
def manage_two_factor(request):
    return {}


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
            return HTTPSeeOther(self.request.route_path("manage.account"))

        totp_secret = self.user_service.get_totp_secret(self.request.user.id)
        if totp_secret:
            return Response(status=403)

        totp_qr = pyqrcode.create(self.default_response["provision_totp_uri"])
        qr_buffer = io.BytesIO()
        totp_qr.svg(qr_buffer, scale=5)

        return Response(content_type="image/svg+xml", body=qr_buffer.getvalue())

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
            return HTTPSeeOther(self.request.route_path("manage.account"))

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
                tag=EventTag.Account.TwoFactorMethodAdded,
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

        form = DeleteTOTPForm(
            request=self.request,
            password=self.request.POST["confirm_password"],
            username=self.request.user.username,
            user_service=self.user_service,
        )

        if form.validate():
            self.user_service.update_user(self.request.user.id, totp_secret=None)
            self.user_service.record_event(
                self.request.user.id,
                tag=EventTag.Account.TwoFactorMethodRemoved,
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
                credential_id=bytes_to_base64url(
                    form.validated_credential.credential_id
                ),
                public_key=bytes_to_base64url(
                    form.validated_credential.credential_public_key
                ),
                sign_count=form.validated_credential.sign_count,
            )
            self.user_service.record_event(
                self.request.user.id,
                tag=EventTag.Account.TwoFactorMethodAdded,
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
                tag=EventTag.Account.TwoFactorMethodRemoved,
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
        self.user_service.record_event(
            self.request.user.id,
            tag=EventTag.Account.RecoveryCodesGenerated,
        )

        return {"recovery_codes": recovery_codes}

    @view_config(
        request_method="GET",
        route_name="manage.account.recovery-codes.regenerate",
        renderer="manage/account/recovery_codes-provision.html",
        require_reauth=10,  # 10 seconds
    )
    def recovery_codes_regenerate(self):
        recovery_codes = self.user_service.generate_recovery_codes(self.request.user.id)
        send_recovery_codes_generated_email(self.request, self.request.user)
        self.user_service.record_event(
            self.request.user.id,
            tag=EventTag.Account.RecoveryCodesRegenerated,
        )

        return {"recovery_codes": recovery_codes}

    @view_config(
        route_name="manage.account.recovery-codes.burn",
        renderer="manage/account/recovery_codes-burn.html",
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
    permission="manage:user",
    renderer="manage/account/token.html",
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
                request=self.request,
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
            )
            self.user_service.record_event(
                self.request.user.id,
                tag=EventTag.Account.APITokenAdded,
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
                        ip_address=self.request.remote_addr,
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
            request=self.request,
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
                tag=EventTag.Account.APITokenRemoved,
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


def user_organizations(request):
    """Return all the organizations for which the user has a privileged role."""
    organizations_managed = (
        request.db.query(Organization.id)
        .join(OrganizationRole.organization)
        .filter(
            OrganizationRole.role_name == OrganizationRoleType.Manager,
            OrganizationRole.user == request.user,
        )
        .subquery()
    )
    organizations_owned = (
        request.db.query(Organization.id)
        .join(OrganizationRole.organization)
        .filter(
            OrganizationRole.role_name == OrganizationRoleType.Owner,
            OrganizationRole.user == request.user,
        )
        .subquery()
    )
    organizations_billing = (
        request.db.query(Organization.id)
        .join(OrganizationRole.organization)
        .filter(
            OrganizationRole.role_name == OrganizationRoleType.BillingManager,
            OrganizationRole.user == request.user,
        )
        .subquery()
    )
    organizations_with_sole_owner = (
        request.db.query(OrganizationRole.organization_id)
        .join(organizations_owned)
        .filter(OrganizationRole.role_name == "Owner")
        .group_by(OrganizationRole.organization_id)
        .having(func.count(OrganizationRole.organization_id) == 1)
        .subquery()
    )
    return {
        "organizations_owned": (
            request.db.query(Organization)
            .join(organizations_owned, Organization.id == organizations_owned.c.id)
            .order_by(Organization.name)
            .all()
        ),
        "organizations_managed": (
            request.db.query(Organization)
            .join(organizations_managed, Organization.id == organizations_managed.c.id)
            .order_by(Organization.name)
            .all()
        ),
        "organizations_billing": (
            request.db.query(Organization)
            .join(organizations_billing, Organization.id == organizations_billing.c.id)
            .order_by(Organization.name)
            .all()
        ),
        "organizations_with_sole_owner": (
            request.db.query(Organization)
            .join(
                organizations_with_sole_owner,
                Organization.id == organizations_with_sole_owner.c.organization_id,
            )
            .order_by(Organization.name)
            .all()
        ),
    }


def organization_owners(request, organization):
    """Return all users who are owners of the organization."""
    owner_roles = (
        request.db.query(User.id)
        .join(OrganizationRole.user)
        .filter(
            OrganizationRole.role_name == OrganizationRoleType.Owner,
            OrganizationRole.organization == organization,
        )
        .subquery()
    )
    return request.db.query(User).join(owner_roles, User.id == owner_roles.c.id).all()


def organization_managers(request, organization):
    """Return all users who are managers of the organization."""
    manager_roles = (
        request.db.query(User.id)
        .join(OrganizationRole.user)
        .filter(
            OrganizationRole.role_name == OrganizationRoleType.Manager,
            OrganizationRole.organization == organization,
        )
        .subquery()
    )
    return (
        request.db.query(User).join(manager_roles, User.id == manager_roles.c.id).all()
    )


def organization_members(request, organization):
    """Return all users who are members of the organization."""
    member_roles = (
        request.db.query(User.id)
        .join(OrganizationRole.user)
        .filter(
            OrganizationRole.role_name == OrganizationRoleType.Member,
            OrganizationRole.organization == organization,
        )
        .subquery()
    )
    return request.db.query(User).join(member_roles, User.id == member_roles.c.id).all()


@view_defaults(
    route_name="manage.organizations",
    renderer="manage/organizations.html",
    uses_session=True,
    require_active_organization=False,  # Allow list/create orgs without active org.
    require_csrf=True,
    require_methods=False,
    permission="manage:user",
    has_translations=True,
)
class ManageOrganizationsViews:
    def __init__(self, request):
        self.request = request
        self.user_service = request.find_service(IUserService, context=None)
        self.organization_service = request.find_service(
            IOrganizationService, context=None
        )

    @property
    def default_response(self):
        all_user_organizations = user_organizations(self.request)

        # Get list of invites as (organization, token) tuples.
        organization_invites = (
            self.organization_service.get_organization_invites_by_user(
                self.request.user.id
            )
        )
        organization_invites = [
            (organization_invite.organization, organization_invite.token)
            for organization_invite in organization_invites
        ]

        # Get list of organizations that are approved (True) or pending (None).
        organizations = self.organization_service.get_organizations_by_user(
            self.request.user.id
        )
        organizations = [
            organization
            for organization in organizations
            if organization.is_approved is not False
        ]

        return {
            "organization_invites": organization_invites,
            "organizations": organizations,
            "organizations_managed": list(
                organization.name
                for organization in all_user_organizations["organizations_managed"]
            ),
            "organizations_owned": list(
                organization.name
                for organization in all_user_organizations["organizations_owned"]
            ),
            "organizations_billing": list(
                organization.name
                for organization in all_user_organizations["organizations_billing"]
            ),
            "create_organization_form": CreateOrganizationForm(
                organization_service=self.organization_service,
            ),
        }

    @view_config(request_method="GET")
    def manage_organizations(self):
        # Organizations must be enabled.
        if self.request.flags.enabled(AdminFlagValue.DISABLE_ORGANIZATIONS):
            raise HTTPNotFound()

        return self.default_response

    @view_config(request_method="POST", request_param=CreateOrganizationForm.__params__)
    def create_organization(self):
        # Organizations must be enabled.
        if self.request.flags.enabled(AdminFlagValue.DISABLE_ORGANIZATIONS):
            raise HTTPNotFound()

        form = CreateOrganizationForm(
            self.request.POST,
            organization_service=self.organization_service,
        )

        if form.validate():
            data = form.data
            organization = self.organization_service.add_organization(**data)
            self.organization_service.record_event(
                organization.id,
                tag=EventTag.Organization.CatalogEntryAdd,
                additional={"submitted_by_user_id": str(self.request.user.id)},
            )
            self.organization_service.record_event(
                organization.id,
                tag=EventTag.Organization.OrganizationCreate,
                additional={"created_by_user_id": str(self.request.user.id)},
            )
            self.organization_service.add_organization_role(
                organization.id,
                self.request.user.id,
                OrganizationRoleType.Owner,
            )
            self.organization_service.record_event(
                organization.id,
                tag=EventTag.Organization.OrganizationRoleAdd,
                additional={
                    "submitted_by_user_id": str(self.request.user.id),
                    "role_name": "Owner",
                    "target_user_id": str(self.request.user.id),
                },
            )
            self.user_service.record_event(
                self.request.user.id,
                tag=EventTag.Account.OrganizationRoleAdd,
                additional={
                    "submitted_by_user_id": str(self.request.user.id),
                    "organization_name": organization.name,
                    "role_name": "Owner",
                },
            )
            send_admin_new_organization_requested_email(
                self.request,
                self.user_service.get_admins(),
                organization_name=organization.name,
                initiator_username=self.request.user.username,
                organization_id=organization.id,
            )
            send_new_organization_requested_email(
                self.request, self.request.user, organization_name=organization.name
            )
            self.request.session.flash(
                "Request for new organization submitted", queue="success"
            )
        else:
            return {"create_organization_form": form}

        if form.orgtype.data == OrganizationType.Company:
            return HTTPSeeOther(
                self.request.route_path(
                    "manage.organization.activate_subscription",
                    organization_name=organization.normalized_name,
                )
            )

        return HTTPSeeOther(self.request.path)


@view_defaults(
    route_name="manage.organization.settings",
    context=Organization,
    renderer="manage/organization/settings.html",
    uses_session=True,
    require_active_organization=True,
    require_csrf=True,
    require_methods=False,
    permission="manage:organization",
    has_translations=True,
    require_reauth=True,
)
class ManageOrganizationSettingsViews:
    def __init__(self, organization, request):
        self.organization = organization
        self.request = request
        self.user_service = request.find_service(IUserService, context=None)
        self.organization_service = request.find_service(
            IOrganizationService, context=None
        )
        self.billing_service = request.find_service(IBillingService, context=None)

    @property
    def active_projects(self):
        return self.organization.projects

    @property
    def default_response(self):
        return {
            "organization": self.organization,
            "save_organization_form": SaveOrganizationForm(
                name=self.organization.name,
                display_name=self.organization.display_name,
                link_url=self.organization.link_url,
                description=self.organization.description,
                orgtype=self.organization.orgtype,
            ),
            "save_organization_name_form": SaveOrganizationNameForm(
                organization_service=self.organization_service,
            ),
            "active_projects": self.active_projects,
        }

    @view_config(request_method="GET", permission="view:organization")
    def manage_organization(self):
        return self.default_response

    @view_config(request_method="POST", request_param=SaveOrganizationForm.__params__)
    def save_organization(self):
        form = SaveOrganizationForm(self.request.POST)

        if form.validate():
            previous_organization_display_name = self.organization.display_name
            previous_organization_link_url = self.organization.link_url
            previous_organization_description = self.organization.description
            previous_organization_orgtype = self.organization.orgtype

            data = form.data
            if previous_organization_orgtype == OrganizationType.Company:
                # Disable changing Company account to Community account.
                data["orgtype"] = previous_organization_orgtype
            self.organization_service.update_organization(self.organization.id, **data)

            owner_users = set(organization_owners(self.request, self.organization))
            send_organization_updated_email(
                self.request,
                owner_users,
                organization_name=self.organization.name,
                organization_display_name=self.organization.display_name,
                organization_link_url=self.organization.link_url,
                organization_description=self.organization.description,
                organization_orgtype=self.organization.orgtype,
                previous_organization_display_name=previous_organization_display_name,
                previous_organization_link_url=previous_organization_link_url,
                previous_organization_description=previous_organization_description,
                previous_organization_orgtype=previous_organization_orgtype,
            )

            self.request.session.flash("Organization details updated", queue="success")

            return HTTPSeeOther(self.request.path)

        return {**self.default_response, "save_organization_form": form}

    @view_config(
        request_method="POST",
        request_param=["confirm_current_organization_name"]
        + SaveOrganizationNameForm.__params__,
    )
    def save_organization_name(self):
        confirm_organization(
            self.organization,
            self.request,
            fail_route="manage.organization.settings",
            field_name="confirm_current_organization_name",
            error_message="Could not rename organization",
        )

        form = SaveOrganizationNameForm(
            self.request.POST,
            organization_service=self.organization_service,
            organization_id=self.organization.id,
        )

        if form.validate():
            previous_organization_name = self.organization.name
            self.organization_service.rename_organization(
                self.organization.id,
                form.name.data,
            )
            self.organization.record_event(
                tag=EventTag.Organization.CatalogEntryAdd,
                ip_address=self.request.remote_addr,
                additional={"submitted_by_user_id": str(self.request.user.id)},
            )
            self.organization.record_event(
                tag=EventTag.Organization.OrganizationRename,
                ip_address=self.request.remote_addr,
                additional={
                    "previous_organization_name": previous_organization_name,
                    "renamed_by_user_id": str(self.request.user.id),
                },
            )
            owner_users = set(organization_owners(self.request, self.organization))
            send_admin_organization_renamed_email(
                self.request,
                self.user_service.get_admins(),
                organization_name=self.organization.name,
                previous_organization_name=previous_organization_name,
            )
            send_organization_renamed_email(
                self.request,
                owner_users,
                organization_name=self.organization.name,
                previous_organization_name=previous_organization_name,
            )
            self.request.session.flash(
                "Organization account name updated", queue="success"
            )
            return HTTPSeeOther(
                self.request.route_path(
                    "manage.organization.settings",
                    organization_name=self.organization.normalized_name,
                )
                + "#modal-close"
            )

        return {**self.default_response, "save_organization_name_form": form}

    @view_config(request_method="POST", request_param=["confirm_organization_name"])
    def delete_organization(self):
        confirm_organization(
            self.organization, self.request, fail_route="manage.organization.settings"
        )

        if self.active_projects:
            self.request.session.flash(
                "Cannot delete organization with active project ownerships",
                queue="error",
            )
            return self.default_response

        # Record event before deleting organization.
        self.organization.record_event(
            tag=EventTag.Organization.OrganizationDelete,
            ip_address=self.request.remote_addr,
            additional={
                "deleted_by_user_id": str(self.request.user.id),
            },
        )

        # Get owners before deleting organization.
        owner_users = set(organization_owners(self.request, self.organization))

        # Cancel any subscriptions tied to this organization.
        if self.organization.subscriptions:
            for subscription in self.organization.subscriptions:
                self.billing_service.cancel_subscription(subscription.subscription_id)

        self.organization_service.delete_organization(self.organization.id)

        send_admin_organization_deleted_email(
            self.request,
            self.user_service.get_admins(),
            organization_name=self.organization.name,
        )
        send_organization_deleted_email(
            self.request,
            owner_users,
            organization_name=self.organization.name,
        )

        return HTTPSeeOther(self.request.route_path("manage.organizations"))


@view_defaults(
    context=Organization,
    uses_session=True,
    require_active_organization=False,  # Allow reactivate billing for inactive org.
    require_csrf=True,
    require_methods=False,
    permission="manage:billing",
    has_translations=True,
    require_reauth=True,
)
class ManageOrganizationBillingViews:
    def __init__(self, organization, request):
        self.organization = organization
        self.request = request
        self.billing_service = request.find_service(IBillingService, context=None)
        self.subscription_service = request.find_service(
            ISubscriptionService, context=None
        )
        self.organization_service = request.find_service(
            IOrganizationService, context=None
        )

    @property
    def customer_id(self):
        if self.organization.customer is None:
            customer = self.billing_service.create_customer(
                name=(
                    self.request.registry.settings["site.name"]
                    + " Organization - "
                    + self.organization.name
                ),
                description=self.organization.description,
            )
            stripe_customer = self.subscription_service.add_stripe_customer(
                customer_id=customer["id"],
            )
            self.organization_service.add_organization_stripe_customer(
                organization_id=self.organization.id,
                stripe_customer_id=stripe_customer.id,
            )
            return customer["id"]
        return self.organization.customer.customer_id

    @property
    def price_id(self):
        # Get or create default subscription price with subscription service.
        default_subscription_price = (
            self.subscription_service.get_or_create_default_subscription_price()
        )
        # Synchronize product and price with billing service.
        self.billing_service.sync_product(
            default_subscription_price.subscription_product
        )
        self.billing_service.sync_price(default_subscription_price)
        return default_subscription_price.price_id

    @property
    def return_url(self):
        return urljoin(
            self.request.application_url,
            self.request.GET.get(
                "next", self.request.route_path("manage.organizations")
            ),
        )

    def create_subscription(self):
        # Create checkout session.
        checkout_session = self.billing_service.create_checkout_session(
            customer_id=self.customer_id,
            price_ids=[self.price_id],
            success_url=self.return_url,
            cancel_url=self.return_url,
        )
        create_subscription_url = checkout_session["url"]
        if isinstance(self.billing_service, MockStripeBillingService):
            # Use local mock of billing UI.
            create_subscription_url = self.request.route_path(
                "mock.billing.checkout-session",
                organization_name=self.organization.normalized_name,
            )
        return HTTPSeeOther(create_subscription_url)

    def manage_subscription(self):
        portal_session = self.billing_service.create_portal_session(
            customer_id=self.customer_id,
            return_url=self.return_url,
        )
        manage_subscription_url = portal_session["url"]
        if isinstance(self.billing_service, MockStripeBillingService):
            # Use local mock of billing UI.
            manage_subscription_url = self.request.route_path(
                "mock.billing.portal-session",
                organization_name=self.organization.normalized_name,
            )
        return HTTPSeeOther(manage_subscription_url)

    @view_config(
        route_name="manage.organization.activate_subscription",
        renderer="manage/organization/activate_subscription.html",
    )
    def activate_subscription(self):
        return {"organization": self.organization}

    @view_config(route_name="manage.organization.subscription")
    def create_or_manage_subscription(self):
        # Organizations must be enabled.
        if self.request.flags.enabled(AdminFlagValue.DISABLE_ORGANIZATIONS):
            raise HTTPNotFound()

        if not self.organization.subscriptions:
            # Create subscription if there are no existing subscription.
            return self.create_subscription()
        else:
            # Manage subscription if there is an existing subscription.
            return self.manage_subscription()


@view_defaults(
    route_name="manage.organization.teams",
    context=Organization,
    renderer="manage/organization/teams.html",
    uses_session=True,
    require_active_organization=True,
    require_csrf=True,
    require_methods=False,
    permission="manage:team",
    has_translations=True,
    require_reauth=True,
)
class ManageOrganizationTeamsViews:
    def __init__(self, organization, request):
        self.organization = organization
        self.request = request
        self.organization_service = request.find_service(
            IOrganizationService, context=None
        )

    @property
    def default_response(self):
        return {
            "organization": self.organization,
            "create_team_form": CreateTeamForm(
                self.request.POST,
                organization_service=self.organization_service,
                organization_id=self.organization.id,
            ),
        }

    @view_config(request_method="GET", permission="view:organization")
    def manage_teams(self):
        return self.default_response

    @view_config(request_method="POST")
    def create_team(self):

        # Get and validate form from default response.
        default_response = self.default_response
        form = default_response["create_team_form"]
        if not form.validate():
            return default_response

        # Add team to organization.
        team = self.organization_service.add_team(
            organization_id=self.organization.id,
            name=form.name.data,
        )

        # Record events.
        self.organization.record_event(
            tag=EventTag.Organization.TeamCreate,
            ip_address=self.request.remote_addr,
            additional={
                "created_by_user_id": str(self.request.user.id),
                "team_name": team.name,
            },
        )
        team.record_event(
            tag=EventTag.Team.TeamCreate,
            ip_address=self.request.remote_addr,
            additional={
                "created_by_user_id": str(self.request.user.id),
            },
        )

        # Send notification emails.
        owner_and_manager_users = set(
            organization_owners(self.request, self.organization)
            + organization_managers(self.request, self.organization)
        )
        send_team_created_email(
            self.request,
            owner_and_manager_users,
            organization_name=self.organization.name,
            team_name=team.name,
        )

        # Display notification message.
        self.request.session.flash(
            f"Created team {team.name!r} in {self.organization.name!r}",
            queue="success",
        )

        # Refresh teams list.
        return HTTPSeeOther(self.request.path)


@view_defaults(
    route_name="manage.organization.projects",
    context=Organization,
    renderer="manage/organization/projects.html",
    uses_session=True,
    require_active_organization=True,
    require_csrf=True,
    require_methods=False,
    permission="manage:organization",
    has_translations=True,
    require_reauth=True,
)
class ManageOrganizationProjectsViews:
    def __init__(self, organization, request):
        self.organization = organization
        self.request = request
        self.user_service = request.find_service(IUserService, context=None)
        self.organization_service = request.find_service(
            IOrganizationService, context=None
        )
        self.project_factory = ProjectFactory(request)

    @property
    def active_projects(self):
        return self.organization.projects

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
        projects_requiring_2fa = {
            project.name for project in all_user_projects["projects_requiring_2fa"]
        }
        project_choices = {
            project.name
            for project in all_user_projects["projects_owned"]
            if not project.organization
        }
        project_factory = self.project_factory

        return {
            "organization": self.organization,
            "active_projects": active_projects,
            "projects_owned": projects_owned,
            "projects_sole_owned": projects_sole_owned,
            "projects_requiring_2fa": projects_requiring_2fa,
            "add_organization_project_form": AddOrganizationProjectForm(
                self.request.POST,
                project_choices=project_choices,
                project_factory=project_factory,
            ),
        }

    @view_config(request_method="GET", permission="view:organization")
    def manage_organization_projects(self):
        return self.default_response

    @view_config(request_method="POST", permission="add:project")
    def add_organization_project(self):
        # Get and validate form from default response.
        default_response = self.default_response
        form = default_response["add_organization_project_form"]
        if not form.validate():
            return default_response

        # Get existing project or add new project.
        if form.add_existing_project.data:
            # Get existing project.
            project = self.project_factory[form.existing_project_name.data]
            # Remove request user as individual project owner.
            role = (
                self.request.db.query(Role)
                .join(User)
                .filter(
                    Role.role_name == "Owner",
                    Role.project == project,
                    Role.user == self.request.user,
                )
                .first()
            )
            if role:
                self.request.db.delete(role)
                self.request.db.add(
                    JournalEntry(
                        name=project.name,
                        action=f"remove {role.role_name} {role.user.username}",
                        submitted_by=self.request.user,
                        submitted_from=self.request.remote_addr,
                    )
                )
                project.record_event(
                    tag=EventTag.Project.RoleRemove,
                    ip_address=self.request.remote_addr,
                    additional={
                        "submitted_by": self.request.user.username,
                        "role_name": role.role_name,
                        "target_user": role.user.username,
                    },
                )
                role.user.record_event(
                    tag=EventTag.Account.RoleRemove,
                    ip_address=self.request.remote_addr,
                    additional={
                        "submitted_by": self.request.user.username,
                        "project_name": project.name,
                        "role_name": role.role_name,
                    },
                )
        else:
            # Validate new project name.
            try:
                validate_project_name(form.new_project_name.data, self.request)
            except HTTPException as exc:
                form.new_project_name.errors.append(exc.detail)
                return default_response

            # Add new project.
            # Note that we pass `creator_is_owner=False`, since the project being
            # created is controlled by the organization and not the user creating it.
            project_service = self.request.find_service(IProjectService)
            project = project_service.create_project(
                form.new_project_name.data,
                self.request.user,
                creator_is_owner=False,
                ratelimited=False,
            )

        # Add project to organization.
        self.organization_service.add_organization_project(
            organization_id=self.organization.id,
            project_id=project.id,
        )

        # Record events.
        self.organization.record_event(
            tag=EventTag.Organization.OrganizationProjectAdd,
            ip_address=self.request.remote_addr,
            additional={
                "submitted_by_user_id": str(self.request.user.id),
                "project_name": project.name,
            },
        )
        project.record_event(
            tag=EventTag.Project.OrganizationProjectAdd,
            ip_address=self.request.remote_addr,
            additional={
                "submitted_by_user_id": str(self.request.user.id),
                "organization_name": self.organization.name,
            },
        )

        # Send notification emails.
        owner_users = set(
            organization_owners(self.request, self.organization)
            + project_owners(self.request, project)
        )
        send_organization_project_added_email(
            self.request,
            owner_users,
            organization_name=self.organization.name,
            project_name=project.name,
        )

        # Display notification message.
        self.request.session.flash(
            f"Added the project {project.name!r} to {self.organization.name!r}",
            queue="success",
        )

        # Refresh projects list.
        return HTTPSeeOther(self.request.path)


@view_config(
    route_name="manage.organization.roles",
    context=Organization,
    renderer="manage/organization/roles.html",
    uses_session=True,
    require_active_organization=True,
    require_methods=False,
    permission="view:organization",
    has_translations=True,
    require_reauth=True,
)
def manage_organization_roles(
    organization, request, _form_class=CreateOrganizationRoleForm
):
    organization_service = request.find_service(IOrganizationService, context=None)
    user_service = request.find_service(IUserService, context=None)
    form = _form_class(
        request.POST,
        orgtype=organization.orgtype,
        organization_service=organization_service,
        user_service=user_service,
    )

    if request.method == "POST" and form.validate():
        username = form.username.data
        role_name = form.role_name.data
        userid = user_service.find_userid(username)
        user = user_service.get_user(userid)
        token_service = request.find_service(ITokenService, name="email")

        existing_role = organization_service.get_organization_role_by_user(
            organization.id, user.id
        )
        organization_invite = organization_service.get_organization_invite_by_user(
            organization.id, user.id
        )
        # Cover edge case where invite is invalid but task
        # has not updated invite status
        try:
            invite_token = token_service.loads(organization_invite.token)
        except (TokenExpired, AttributeError):
            invite_token = None

        if existing_role:
            request.session.flash(
                request._(
                    "User '${username}' already has ${role_name} role for organization",
                    mapping={
                        "username": username,
                        "role_name": existing_role.role_name.value,
                    },
                ),
                queue="error",
            )
        elif user.primary_email is None or not user.primary_email.verified:
            request.session.flash(
                request._(
                    "User '${username}' does not have a verified primary email "
                    "address and cannot be added as a ${role_name} for organization",
                    mapping={"username": username, "role_name": role_name.value},
                ),
                queue="error",
            )
        elif (
            organization_invite
            and organization_invite.invite_status
            == OrganizationInvitationStatus.Pending
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
                    "action": "email-organization-role-verify",
                    "desired_role": role_name.value,
                    "user_id": user.id,
                    "organization_id": organization.id,
                    "submitter_id": request.user.id,
                }
            )
            if organization_invite:
                organization_invite.invite_status = OrganizationInvitationStatus.Pending
                organization_invite.token = invite_token
            else:
                organization_service.add_organization_invite(
                    organization_id=organization.id,
                    user_id=user.id,
                    invite_token=invite_token,
                )
            organization.record_event(
                tag=EventTag.Organization.OrganizationRoleInvite,
                ip_address=request.remote_addr,
                additional={
                    "submitted_by_user_id": str(request.user.id),
                    "role_name": role_name.value,
                    "target_user_id": str(userid),
                },
            )
            user.record_event(
                tag=EventTag.Account.OrganizationRoleInvite,
                ip_address=request.remote_addr,
                additional={
                    "submitted_by_user_id": str(request.user.id),
                    "organization_name": organization.name,
                    "role_name": role_name.value,
                },
            )
            request.db.flush()  # in order to get id
            owner_users = set(organization_owners(request, organization))
            send_organization_member_invited_email(
                request,
                owner_users,
                user=user,
                desired_role=role_name.value,
                initiator_username=request.user.username,
                organization_name=organization.name,
                email_token=invite_token,
                token_age=token_service.max_age,
            )
            send_organization_role_verification_email(
                request,
                user,
                desired_role=role_name.value,
                initiator_username=request.user.username,
                organization_name=organization.name,
                email_token=invite_token,
                token_age=token_service.max_age,
            )
            request.session.flash(
                request._(
                    "Invitation sent to '${username}'",
                    mapping={"username": username},
                ),
                queue="success",
            )

        return HTTPSeeOther(request.path)

    roles = set(organization_service.get_organization_roles(organization.id))
    invitations = set(organization_service.get_organization_invites(organization.id))

    return {
        "organization": organization,
        "roles": roles,
        "invitations": invitations,
        "form": form,
        "organizations_with_sole_owner": list(
            organization.name
            for organization in user_organizations(request)[
                "organizations_with_sole_owner"
            ]
        ),
    }


@view_config(
    route_name="manage.organization.revoke_invite",
    context=Organization,
    uses_session=True,
    require_active_organization=True,
    require_methods=["POST"],
    permission="manage:organization",
    has_translations=True,
)
def revoke_organization_invitation(organization, request):
    organization_service = request.find_service(IOrganizationService, context=None)
    user_service = request.find_service(IUserService, context=None)
    token_service = request.find_service(ITokenService, name="email")
    user = user_service.get_user(request.POST["user_id"])

    organization_invite = organization_service.get_organization_invite_by_user(
        organization.id, user.id
    )
    if organization_invite is None:
        request.session.flash(
            request._("Could not find organization invitation."), queue="error"
        )
        return HTTPSeeOther(
            request.route_path(
                "manage.organization.roles",
                organization_name=organization.normalized_name,
            )
        )

    organization_service.delete_organization_invite(organization_invite.id)

    try:
        token_data = token_service.loads(organization_invite.token)
    except TokenExpired:
        request.session.flash(request._("Invitation already expired."), queue="success")
        return HTTPSeeOther(
            request.route_path(
                "manage.organization.roles",
                organization_name=organization.normalized_name,
            )
        )
    role_name = token_data.get("desired_role")

    organization.record_event(
        tag=EventTag.Organization.OrganizationRoleRevokeInvite,
        ip_address=request.remote_addr,
        additional={
            "submitted_by_user_id": str(request.user.id),
            "role_name": role_name,
            "target_user_id": str(user.id),
        },
    )
    user.record_event(
        tag=EventTag.Account.OrganizationRoleRevokeInvite,
        ip_address=request.remote_addr,
        additional={
            "submitted_by_user_id": str(request.user.id),
            "organization_name": organization.name,
            "role_name": role_name,
        },
    )

    owner_users = set(organization_owners(request, organization))
    send_organization_member_invite_canceled_email(
        request,
        owner_users,
        user=user,
        organization_name=organization.name,
    )
    send_canceled_as_invited_organization_member_email(
        request,
        user,
        organization_name=organization.name,
    )

    request.session.flash(
        request._(
            "Invitation revoked from '${username}'.",
            mapping={"username": user.username},
        ),
        queue="success",
    )

    return HTTPSeeOther(
        request.route_path(
            "manage.organization.roles", organization_name=organization.normalized_name
        )
    )


@view_config(
    route_name="manage.organization.change_role",
    context=Organization,
    uses_session=True,
    require_active_organization=True,
    require_methods=["POST"],
    permission="manage:organization",
    has_translations=True,
    require_reauth=True,
)
def change_organization_role(
    organization, request, _form_class=ChangeOrganizationRoleForm
):
    form = _form_class(request.POST, orgtype=organization.orgtype)

    if form.validate():
        organization_service = request.find_service(IOrganizationService, context=None)
        role_id = request.POST["role_id"]
        role = organization_service.get_organization_role(role_id)
        if not role or role.organization_id != organization.id:
            request.session.flash("Could not find member", queue="error")
        elif role.role_name == OrganizationRoleType.Owner and role.user == request.user:
            request.session.flash("Cannot remove yourself as Owner", queue="error")
        else:
            role.role_name = form.role_name.data

            owner_users = set(organization_owners(request, organization))
            # Don't send owner notification email to new user
            # if they are now an owner
            owner_users.discard(role.user)

            send_organization_member_role_changed_email(
                request,
                owner_users,
                user=role.user,
                submitter=request.user,
                organization_name=organization.name,
                role=role.role_name.value,
            )

            send_role_changed_as_organization_member_email(
                request,
                role.user,
                submitter=request.user,
                organization_name=organization.name,
                role=role.role_name.value,
            )

            organization.record_event(
                tag=EventTag.Organization.OrganizationRoleChange,
                ip_address=request.remote_addr,
                additional={
                    "submitted_by_user_id": str(request.user.id),
                    "role_name": form.role_name.data,
                    "target_user_id": str(role.user.id),
                },
            )
            role.user.record_event(
                tag=EventTag.Account.OrganizationRoleChange,
                ip_address=request.remote_addr,
                additional={
                    "submitted_by_user_id": str(request.user.id),
                    "organization_name": organization.name,
                    "role_name": form.role_name.data,
                },
            )

            request.session.flash("Changed role", queue="success")

    return HTTPSeeOther(
        request.route_path(
            "manage.organization.roles", organization_name=organization.normalized_name
        )
    )


@view_config(
    route_name="manage.organization.delete_role",
    context=Organization,
    uses_session=True,
    require_active_organization=True,
    require_methods=["POST"],
    permission="view:organization",
    has_translations=True,
    require_reauth=True,
)
def delete_organization_role(organization, request):
    organization_service = request.find_service(IOrganizationService, context=None)
    role_id = request.POST["role_id"]
    role = organization_service.get_organization_role(role_id)
    organizations_sole_owned = {
        organization.id
        for organization in user_organizations(request)["organizations_with_sole_owner"]
    }
    is_sole_owner = organization.id in organizations_sole_owned

    if not role or role.organization_id != organization.id:
        request.session.flash("Could not find member", queue="error")
    elif (
        not request.has_permission("manage:organization") and role.user != request.user
    ):
        request.session.flash(
            "Cannot remove other people from the organization", queue="error"
        )
    elif (
        role.role_name == OrganizationRoleType.Owner
        and role.user == request.user
        and is_sole_owner
    ):
        request.session.flash("Cannot remove yourself as Sole Owner", queue="error")
    else:
        organization_service.delete_organization_role(role.id)
        organization.record_event(
            tag=EventTag.Organization.OrganizationRoleRemove,
            ip_address=request.remote_addr,
            additional={
                "submitted_by_user_id": str(request.user.id),
                "role_name": role.role_name.value,
                "target_user_id": str(role.user.id),
            },
        )
        role.user.record_event(
            tag=EventTag.Account.OrganizationRoleRemove,
            ip_address=request.remote_addr,
            additional={
                "submitted_by_user_id": str(request.user.id),
                "organization_name": organization.name,
                "role_name": role.role_name.value,
            },
        )

        owner_users = set(organization_owners(request, organization))
        # Don't send owner notification email to new user
        # if they are now an owner
        owner_users.discard(role.user)

        send_organization_member_removed_email(
            request,
            owner_users,
            user=role.user,
            submitter=request.user,
            organization_name=organization.name,
        )

        send_removed_as_organization_member_email(
            request,
            role.user,
            submitter=request.user,
            organization_name=organization.name,
        )

        request.session.flash("Removed from organization", queue="success")

    if role and role.user == request.user:
        # User removed self from organization.
        return HTTPSeeOther(request.route_path("manage.organizations"))
    else:
        return HTTPSeeOther(
            request.route_path(
                "manage.organization.roles",
                organization_name=organization.normalized_name,
            )
        )


@view_config(
    route_name="manage.organization.history",
    context=Organization,
    renderer="manage/organization/history.html",
    uses_session=True,
    permission="manage:organization",
    has_translations=True,
)
def manage_organization_history(organization, request):
    try:
        page_num = int(request.params.get("page", 1))
    except ValueError:
        raise HTTPBadRequest("'page' must be an integer.")

    events_query = (
        request.db.query(Organization.Event)
        .join(Organization.Event.source)
        .filter(Organization.Event.source_id == organization.id)
        .order_by(Organization.Event.time.desc())
        .order_by(Organization.Event.tag.desc())
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
        "organization": organization,
    }


@view_defaults(
    route_name="manage.team.settings",
    context=Team,
    renderer="manage/team/settings.html",
    uses_session=True,
    require_active_organization=True,
    require_csrf=True,
    require_methods=False,
    permission="manage:team",
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
                name=self.team.name,
                organization_service=self.organization_service,
                organization_id=self.team.organization_id,
                team_id=self.team.id,
            ),
        }

    @view_config(request_method="GET", permission="view:team")
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
                ip_address=self.request.remote_addr,
                additional={
                    "team_name": self.team.name,
                    "previous_team_name": previous_team_name,
                    "renamed_by_user_id": str(self.request.user.id),
                },
            )
            self.team.record_event(
                tag=EventTag.Team.TeamRename,
                ip_address=self.request.remote_addr,
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
            ip_address=self.request.remote_addr,
            additional={
                "deleted_by_user_id": str(self.request.user.id),
                "team_name": team_name,
            },
        )
        self.team.record_event(
            tag=EventTag.Team.TeamDelete,
            ip_address=self.request.remote_addr,
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
    permission="manage:team",
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
        projects_requiring_2fa = {
            project.name for project in all_user_projects["projects_requiring_2fa"]
        }

        return {
            "team": self.team,
            "active_projects": active_projects,
            "projects_owned": projects_owned,
            "projects_sole_owned": projects_sole_owned,
            "projects_requiring_2fa": projects_requiring_2fa,
        }

    @view_config(request_method="GET", permission="view:team")
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
    permission="manage:team",
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

    @view_config(request_method="GET", permission="view:team")
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
            ip_address=self.request.remote_addr,
            additional={
                "submitted_by_user_id": str(self.request.user.id),
                "team_name": self.team.name,
                "role_name": role_name.value,
                "target_user_id": str(user_id),
            },
        )
        self.team.record_event(
            tag=EventTag.Team.TeamRoleAdd,
            ip_address=self.request.remote_addr,
            additional={
                "submitted_by_user_id": str(self.request.user.id),
                "role_name": role_name.value,
                "target_user_id": str(user_id),
            },
        )
        role.user.record_event(
            tag=EventTag.Account.TeamRoleAdd,
            ip_address=self.request.remote_addr,
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
        permission="view:team",
    )
    def delete_team_role(self):
        # Get team role.
        role_id = self.request.POST["role_id"]
        role = self.organization_service.get_team_role(role_id)

        if not role or role.team_id != self.team.id:
            self.request.session.flash("Could not find member", queue="error")
        elif (
            not self.request.has_permission("manage:team")
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
                ip_address=self.request.remote_addr,
                additional={
                    "submitted_by_user_id": str(self.request.user.id),
                    "team_name": self.team.name,
                    "role_name": role.role_name.value,
                    "target_user_id": str(role.user.id),
                },
            )
            self.team.record_event(
                tag=EventTag.Team.TeamRoleRemove,
                ip_address=self.request.remote_addr,
                additional={
                    "submitted_by_user_id": str(self.request.user.id),
                    "role_name": role.role_name.value,
                    "target_user_id": str(role.user.id),
                },
            )
            role.user.record_event(
                tag=EventTag.Account.TeamRoleRemove,
                ip_address=self.request.remote_addr,
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
    permission="manage:team",
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

    projects = set(request.user.projects)

    all_user_projects = user_projects(request)
    projects |= set(all_user_projects["projects_owned"])
    projects_owned = {project.name for project in all_user_projects["projects_owned"]}
    projects_sole_owned = {
        project.name for project in all_user_projects["projects_sole_owned"]
    }
    projects_requiring_2fa = {
        project.name for project in all_user_projects["projects_requiring_2fa"]
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
        "projects_requiring_2fa": projects_requiring_2fa,
        "project_invites": project_invites,
    }


@view_defaults(
    route_name="manage.project.settings",
    context=Project,
    renderer="manage/project/settings.html",
    uses_session=True,
    permission="manage:project",
    has_translations=True,
    require_reauth=True,
    require_methods=False,
)
class ManageProjectSettingsViews:
    def __init__(self, project, request):
        self.project = project
        self.request = request
        self.toggle_2fa_requirement_form_class = Toggle2FARequirementForm
        self.transfer_organization_project_form_class = TransferOrganizationProjectForm

    @view_config(request_method="GET")
    def manage_project_settings(self):
        if self.request.flags.enabled(AdminFlagValue.DISABLE_ORGANIZATIONS):
            # Disable transfer of project to any organization.
            organization_choices = set()
        else:
            # Allow transfer of project to active orgs owned or managed by user.
            all_user_organizations = user_organizations(self.request)
            active_organizations_owned = {
                organization.name
                for organization in all_user_organizations["organizations_owned"]
                if organization.is_active
            }
            active_organizations_managed = {
                organization.name
                for organization in all_user_organizations["organizations_managed"]
                if organization.is_active
            }
            current_organization = (
                {self.project.organization.name} if self.project.organization else set()
            )
            organization_choices = (
                active_organizations_owned | active_organizations_managed
            ) - current_organization

        return {
            "project": self.project,
            "MAX_FILESIZE": MAX_FILESIZE,
            "MAX_PROJECT_SIZE": MAX_PROJECT_SIZE,
            "toggle_2fa_form": self.toggle_2fa_requirement_form_class(),
            "transfer_organization_project_form": (
                self.transfer_organization_project_form_class(
                    organization_choices=organization_choices,
                )
            ),
        }

    @view_config(
        request_method="POST",
        request_param=Toggle2FARequirementForm.__params__,
        require_reauth=True,
    )
    def toggle_2fa_requirement(self):
        if not self.request.registry.settings[
            "warehouse.two_factor_requirement.enabled"
        ]:
            raise HTTPNotFound

        if self.project.pypi_mandates_2fa:
            self.request.session.flash(
                "2FA requirement cannot be disabled for critical projects",
                queue="error",
            )
        elif self.project.owners_require_2fa:
            self.project.owners_require_2fa = False
            self.project.record_event(
                tag=EventTag.Project.OwnersRequire2FADisabled,
                ip_address=self.request.remote_addr,
                additional={"modified_by": self.request.user.username},
            )
            self.request.session.flash(
                f"2FA requirement disabled for { self.project.name }",
                queue="success",
            )
        else:
            self.project.owners_require_2fa = True
            self.project.record_event(
                tag=EventTag.Project.OwnersRequire2FAEnabled,
                ip_address=self.request.remote_addr,
                additional={"modified_by": self.request.user.username},
            )
            self.request.session.flash(
                f"2FA requirement enabled for { self.project.name }",
                queue="success",
            )

        return HTTPSeeOther(
            self.request.route_path(
                "manage.project.settings", project_name=self.project.name
            )
        )


@view_defaults(
    context=Project,
    route_name="manage.project.settings.publishing",
    renderer="manage/project/publishing.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    permission="manage:project",
    has_translations=True,
    require_reauth=True,
    http_cache=0,
)
class ManageOIDCPublisherViews:
    def __init__(self, project, request):
        self.request = request
        self.project = project
        self.oidc_enabled = self.request.registry.settings["warehouse.oidc.enabled"]
        self.metrics = self.request.find_service(IMetricsService, context=None)

    @property
    def _ratelimiters(self):
        return {
            "user.oidc": self.request.find_service(
                IRateLimiter, name="user_oidc.publisher.register"
            ),
            "ip.oidc": self.request.find_service(
                IRateLimiter, name="ip_oidc.publisher.register"
            ),
        }

    def _hit_ratelimits(self):
        self._ratelimiters["user.oidc"].hit(self.request.user.id)
        self._ratelimiters["ip.oidc"].hit(self.request.remote_addr)

    def _check_ratelimits(self):
        if not self._ratelimiters["user.oidc"].test(self.request.user.id):
            raise TooManyOIDCRegistrations(
                resets_in=self._ratelimiters["user.oidc"].resets_in(
                    self.request.user.id
                )
            )

        if not self._ratelimiters["ip.oidc"].test(self.request.remote_addr):
            raise TooManyOIDCRegistrations(
                resets_in=self._ratelimiters["ip.oidc"].resets_in(
                    self.request.remote_addr
                )
            )

    @property
    def github_publisher_form(self):
        return GitHubPublisherForm(
            self.request.POST,
            api_token=self.request.registry.settings.get("github.token"),
        )

    @property
    def default_response(self):
        return {
            "oidc_enabled": self.oidc_enabled,
            "project": self.project,
            "github_publisher_form": self.github_publisher_form,
        }

    @view_config(request_method="GET")
    def manage_project_oidc_publishers(self):
        if not self.oidc_enabled:
            raise HTTPNotFound

        if self.request.flags.enabled(AdminFlagValue.DISALLOW_OIDC):
            self.request.session.flash(
                (
                    "OpenID Connect is temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )

        return self.default_response

    @view_config(request_method="POST", request_param=GitHubPublisherForm.__params__)
    def add_github_oidc_publisher(self):
        if not self.oidc_enabled:
            raise HTTPNotFound

        if self.request.flags.enabled(AdminFlagValue.DISALLOW_OIDC):
            self.request.session.flash(
                (
                    "OpenID Connect is temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )
            return self.default_response

        self.metrics.increment(
            "warehouse.oidc.add_publisher.attempt", tags=["publisher:GitHub"]
        )

        try:
            self._check_ratelimits()
        except TooManyOIDCRegistrations as exc:
            self.metrics.increment(
                "warehouse.oidc.add_publisher.ratelimited", tags=["publisher:GitHub"]
            )
            return HTTPTooManyRequests(
                self.request._(
                    "There have been too many attempted OpenID Connect registrations. "
                    "Try again later."
                ),
                retry_after=exc.resets_in.total_seconds(),
            )

        self._hit_ratelimits()

        response = self.default_response
        form = response["github_publisher_form"]

        if form.validate():
            # GitHub OIDC publishers are unique on the tuple of
            # (repository_name, repository_owner, workflow_filename), so we check for
            # an already registered one before creating.
            publisher = (
                self.request.db.query(GitHubPublisher)
                .filter(
                    GitHubPublisher.repository_name == form.repository.data,
                    GitHubPublisher.repository_owner == form.normalized_owner,
                    GitHubPublisher.workflow_filename == form.workflow_filename.data,
                )
                .one_or_none()
            )
            if publisher is None:
                publisher = GitHubPublisher(
                    repository_name=form.repository.data,
                    repository_owner=form.normalized_owner,
                    repository_owner_id=form.owner_id,
                    workflow_filename=form.workflow_filename.data,
                )

                self.request.db.add(publisher)

            # Each project has a unique set of OIDC publishers; the same
            # publisher can't be registered to the project more than once.
            if publisher in self.project.oidc_publishers:
                self.request.session.flash(
                    f"{publisher} is already registered with {self.project.name}",
                    queue="error",
                )
                return response

            for user in self.project.users:
                send_oidc_publisher_added_email(
                    self.request,
                    user,
                    project_name=self.project.name,
                    publisher=publisher,
                )

            self.project.oidc_publishers.append(publisher)

            self.project.record_event(
                tag=EventTag.Project.OIDCPublisherAdded,
                ip_address=self.request.remote_addr,
                additional={
                    "publisher": publisher.publisher_name,
                    "id": str(publisher.id),
                    "specifier": str(publisher),
                },
            )

            self.request.session.flash(
                f"Added {publisher} to {self.project.name}",
                queue="success",
            )

            self.metrics.increment(
                "warehouse.oidc.add_publisher.ok", tags=["publisher:GitHub"]
            )

            return HTTPSeeOther(self.request.path)

        return response

    @view_config(request_method="POST", request_param=DeletePublisherForm.__params__)
    def delete_oidc_publisher(self):
        if not self.oidc_enabled:
            raise HTTPNotFound

        if self.request.flags.enabled(AdminFlagValue.DISALLOW_OIDC):
            self.request.session.flash(
                (
                    "OpenID Connect is temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )
            return self.default_response

        self.metrics.increment("warehouse.oidc.delete_publisher.attempt")

        form = DeletePublisherForm(self.request.POST)

        if form.validate():
            publisher = self.request.db.query(OIDCPublisher).get(form.publisher_id.data)

            # publisher will be `None` here if someone manually futzes with the form.
            if publisher is None or publisher not in self.project.oidc_publishers:
                self.request.session.flash(
                    "Invalid publisher for project",
                    queue="error",
                )
                return self.default_response

            for user in self.project.users:
                send_oidc_publisher_removed_email(
                    self.request,
                    user,
                    project_name=self.project.name,
                    publisher=publisher,
                )

            # We remove this publisher from the project's list of publishers
            # and, if there are no projects left associated with the publisher,
            # we delete it entirely.
            self.project.oidc_publishers.remove(publisher)
            if len(publisher.projects) == 0:
                self.request.db.delete(publisher)

            self.project.record_event(
                tag=EventTag.Project.OIDCPublisherRemoved,
                ip_address=self.request.remote_addr,
                additional={
                    "publisher": publisher.publisher_name,
                    "id": str(publisher.id),
                    "specifier": str(publisher),
                },
            )

            self.request.session.flash(
                f"Removed {publisher} from {self.project.name}", queue="success"
            )

            self.metrics.increment(
                "warehouse.oidc.delete_publisher.ok",
                tags=[f"publisher:{publisher.publisher_name}"],
            )

            return HTTPSeeOther(self.request.path)

        return self.default_response


@view_config(
    route_name="manage.project.remove_organization_project",
    context=Project,
    uses_session=True,
    require_methods=["POST"],
    permission="manage:project",
    has_translations=True,
    require_reauth=True,
)
def remove_organization_project(project, request):
    if request.flags.enabled(AdminFlagValue.DISABLE_ORGANIZATIONS):
        request.session.flash("Organizations are disabled", queue="error")
        return HTTPSeeOther(
            request.route_path("manage.project.settings", project_name=project.name)
        )

    if (
        # Check that user has permission to remove projects from organization.
        (project.organization and request.user not in project.organization.owners)
        # Check that project has an individual owner.
        or not project_owners(request, project)
    ):
        request.session.flash(
            (
                "Could not remove project from organization - "
                "you do not have the required permissions"
            ),
            queue="error",
        )
        return HTTPSeeOther(
            request.route_path("manage.project.settings", project_name=project.name)
        )

    confirm_project(
        project,
        request,
        fail_route="manage.project.settings",
        field_name="confirm_remove_organization_project_name",
        error_message="Could not remove project from organization",
    )

    # Remove project from current organization.
    organization_service = request.find_service(IOrganizationService, context=None)
    if organization := project.organization:
        organization_service.delete_organization_project(organization.id, project.id)
        organization.record_event(
            tag=EventTag.Organization.OrganizationProjectRemove,
            ip_address=request.remote_addr,
            additional={
                "submitted_by_user_id": str(request.user.id),
                "project_name": project.name,
            },
        )
        project.record_event(
            tag=EventTag.Project.OrganizationProjectRemove,
            ip_address=request.remote_addr,
            additional={
                "submitted_by_user_id": str(request.user.id),
                "organization_name": organization.name,
            },
        )
        # Send notification emails.
        owner_users = set(
            organization_owners(request, organization)
            + project_owners(request, project)
        )
        send_organization_project_removed_email(
            request,
            owner_users,
            organization_name=organization.name,
            project_name=project.name,
        )
        # Display notification message.
        request.session.flash(
            f"Removed the project {project.name!r} from {organization.name!r}",
            queue="success",
        )

        return HTTPSeeOther(
            request.route_path(
                "manage.organization.projects",
                organization_name=organization.normalized_name,
            )
        )

    request.session.flash(
        ("Could not remove project from organization - no organization found"),
        queue="error",
    )
    return HTTPSeeOther(
        request.route_path("manage.project.settings", project_name=project.name)
    )


@view_config(
    route_name="manage.project.transfer_organization_project",
    context=Project,
    uses_session=True,
    require_methods=["POST"],
    permission="manage:project",
    has_translations=True,
    require_reauth=True,
)
def transfer_organization_project(project, request):
    if request.flags.enabled(AdminFlagValue.DISABLE_ORGANIZATIONS):
        request.session.flash("Organizations are disabled", queue="error")
        return HTTPSeeOther(
            request.route_path("manage.project.settings", project_name=project.name)
        )

    # Check that user has permission to remove projects from organization.
    if project.organization and request.user not in project.organization.owners:
        request.session.flash(
            "Could not transfer project - you do not have the required permissions",
            queue="error",
        )
        return HTTPSeeOther(
            request.route_path("manage.project.settings", project_name=project.name)
        )

    confirm_project(
        project,
        request,
        fail_route="manage.project.settings",
        field_name="confirm_transfer_organization_project_name",
        error_message="Could not transfer project",
    )

    all_user_organizations = user_organizations(request)
    active_organizations_owned = {
        organization.name
        for organization in all_user_organizations["organizations_owned"]
        if organization.is_active
    }
    active_organizations_managed = {
        organization.name
        for organization in all_user_organizations["organizations_managed"]
        if organization.is_active
    }
    current_organization = (
        {project.organization.name} if project.organization else set()
    )
    organization_choices = (
        active_organizations_owned | active_organizations_managed
    ) - current_organization

    form = TransferOrganizationProjectForm(
        request.POST,
        organization_choices=organization_choices,
    )

    if not form.validate():
        for error_list in form.errors.values():
            for error in error_list:
                request.session.flash(error, queue="error")
        return HTTPSeeOther(
            request.route_path("manage.project.settings", project_name=project.name)
        )

    # Remove request user as individual project owner.
    role = (
        request.db.query(Role)
        .join(User)
        .filter(
            Role.role_name == "Owner",
            Role.project == project,
            Role.user == request.user,
        )
        .first()
    )
    if role:
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
            tag=EventTag.Project.RoleRemove,
            ip_address=request.remote_addr,
            additional={
                "submitted_by": request.user.username,
                "role_name": role.role_name,
                "target_user": role.user.username,
            },
        )

    # Remove project from current organization.
    organization_service = request.find_service(IOrganizationService, context=None)
    if organization := project.organization:
        organization_service.delete_organization_project(organization.id, project.id)
        organization.record_event(
            tag=EventTag.Organization.OrganizationProjectRemove,
            ip_address=request.remote_addr,
            additional={
                "submitted_by_user_id": str(request.user.id),
                "project_name": project.name,
            },
        )
        project.record_event(
            tag=EventTag.Project.OrganizationProjectRemove,
            ip_address=request.remote_addr,
            additional={
                "submitted_by_user_id": str(request.user.id),
                "organization_name": organization.name,
            },
        )
        # Send notification emails.
        owner_users = set(
            organization_owners(request, organization)
            + project_owners(request, project)
        )
        send_organization_project_removed_email(
            request,
            owner_users,
            organization_name=organization.name,
            project_name=project.name,
        )

    # Add project to selected organization.
    organization = organization_service.get_organization_by_name(form.organization.data)
    organization_service.add_organization_project(organization.id, project.id)
    organization.record_event(
        tag=EventTag.Organization.OrganizationProjectAdd,
        ip_address=request.remote_addr,
        additional={
            "submitted_by_user_id": str(request.user.id),
            "project_name": project.name,
        },
    )
    project.record_event(
        tag=EventTag.Project.OrganizationProjectAdd,
        ip_address=request.remote_addr,
        additional={
            "submitted_by_user_id": str(request.user.id),
            "organization_name": organization.name,
        },
    )

    # Send notification emails.
    owner_users = set(
        organization_owners(request, organization) + project_owners(request, project)
    )
    send_organization_project_added_email(
        request,
        owner_users,
        organization_name=organization.name,
        project_name=project.name,
    )

    request.session.flash(
        f"Transferred the project {project.name!r} to {organization.name!r}",
        queue="success",
    )

    return HTTPSeeOther(
        request.route_path("manage.project.settings", project_name=project.name)
    )


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
        # If this is an organzation project check to see if user is Org Owner
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
    renderer="manage/project/releases.html",
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
    renderer="manage/project/release.html",
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
            tag=EventTag.Project.ReleaseYank,
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
            tag=EventTag.Project.ReleaseUnyank,
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
            tag=EventTag.Project.ReleaseRemove,
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
            tag=EventTag.Project.ReleaseFileRemove,
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
    renderer="manage/project/roles.html",
    uses_session=True,
    require_methods=False,
    permission="manage:project",
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
        not request.flags.enabled(AdminFlagValue.DISABLE_ORGANIZATIONS)
        and project.organization
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
                submitted_from=request.remote_addr,
            )
        )

        # Record events.
        project.record_event(
            tag=EventTag.Project.TeamProjectRoleAdd,
            ip_address=request.remote_addr,
            additional={
                "submitted_by_user_id": str(request.user.id),
                "role_name": role_name.value,
                "target_team": team.name,
            },
        )
        team.organization.record_event(
            tag=EventTag.Organization.TeamProjectRoleAdd,
            ip_address=request.remote_addr,
            additional={
                "submitted_by_user_id": str(request.user.id),
                "project_name": project.name,
                "role_name": role_name.value,
                "target_team": team.name,
            },
        )
        team.record_event(
            tag=EventTag.Team.TeamProjectRoleAdd,
            ip_address=request.remote_addr,
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
                submitted_from=request.remote_addr,
            )
        )

        # Record events.
        project.record_event(
            tag=EventTag.Project.RoleAdd,
            ip_address=request.remote_addr,
            additional={
                "submitted_by": request.user.username,
                "role_name": role_name,
                "target_user": user.username,
            },
        )
        user.record_event(
            tag=EventTag.Account.RoleAdd,
            ip_address=request.remote_addr,
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
                tag=EventTag.Project.RoleInvite,
                ip_address=request.remote_addr,
                additional={
                    "submitted_by": request.user.username,
                    "role_name": role_name,
                    "target_user": username,
                },
            )
            user.record_event(
                tag=EventTag.Account.RoleInvite,
                ip_address=request.remote_addr,
                additional={
                    "submitted_by": request.user.username,
                    "project_name": project.name,
                    "role_name": role_name,
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

        # Refresh project collaborators.
        return HTTPSeeOther(request.path)


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
        tag=EventTag.Project.RoleRevokeInvite,
        ip_address=request.remote_addr,
        additional={
            "submitted_by": request.user.username,
            "role_name": role_name,
            "target_user": user.username,
        },
    )
    user.record_event(
        tag=EventTag.Account.RoleRevokeInvite,
        ip_address=request.remote_addr,
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
                    tag=EventTag.Project.RoleChange,
                    ip_address=request.remote_addr,
                    additional={
                        "submitted_by": request.user.username,
                        "role_name": form.role_name.data,
                        "target_user": role.user.username,
                    },
                )
                role.user.record_event(
                    tag=EventTag.Account.RoleChange,
                    ip_address=request.remote_addr,
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
    permission="manage:project",
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
                    submitted_from=request.remote_addr,
                )
            )
            project.record_event(
                tag=EventTag.Project.RoleRemove,
                ip_address=request.remote_addr,
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
    route_name="manage.project.change_team_project_role",
    context=Project,
    uses_session=True,
    require_methods=["POST"],
    permission="manage:project",
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
                        submitted_from=request.remote_addr,
                    )
                )

                # Change team project role.
                role.role_name = form.team_project_role_name.data

                # Record events.
                project.record_event(
                    tag=EventTag.Project.TeamProjectRoleChange,
                    ip_address=request.remote_addr,
                    additional={
                        "submitted_by_user_id": str(request.user.id),
                        "role_name": role.role_name.value,
                        "target_team": role.team.name,
                    },
                )
                role.team.organization.record_event(
                    tag=EventTag.Organization.TeamProjectRoleChange,
                    ip_address=request.remote_addr,
                    additional={
                        "submitted_by_user_id": str(request.user.id),
                        "project_name": role.project.name,
                        "role_name": role.role_name.value,
                        "target_team": role.team.name,
                    },
                )
                role.team.record_event(
                    tag=EventTag.Team.TeamProjectRoleChange,
                    ip_address=request.remote_addr,
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
    permission="manage:project",
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
                    submitted_from=request.remote_addr,
                )
            )

            # Record event.
            project.record_event(
                tag=EventTag.Project.TeamProjectRoleRemove,
                ip_address=request.remote_addr,
                additional={
                    "submitted_by_user_id": str(request.user.id),
                    "role_name": role_name.value,
                    "target_team": team.name,
                },
            )
            team.organization.record_event(
                tag=EventTag.Organization.TeamProjectRoleRemove,
                ip_address=request.remote_addr,
                additional={
                    "submitted_by_user_id": str(request.user.id),
                    "project_name": project.name,
                    "role_name": role_name.value,
                    "target_team": team.name,
                },
            )
            team.record_event(
                tag=EventTag.Team.TeamProjectRoleRemove,
                ip_address=request.remote_addr,
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


@view_config(
    route_name="manage.project.history",
    context=Project,
    renderer="manage/project/history.html",
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
        request.db.query(Project.Event)
        .join(Project.Event.source)
        .filter(Project.Event.source_id == project.id)
        .order_by(Project.Event.time.desc())
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
    renderer="manage/project/documentation.html",
    uses_session=True,
    permission="manage:project",
    has_translations=True,
)
def manage_project_documentation(project, request):
    return {"project": project}
