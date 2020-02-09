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

import datetime
import hashlib
import json
import uuid

from first import first
from pyramid.httpexceptions import (
    HTTPMovedPermanently,
    HTTPSeeOther,
    HTTPTooManyRequests,
)
from pyramid.response import Response
from pyramid.security import forget, remember
from pyramid.view import view_config
from sqlalchemy.orm.exc import NoResultFound

from warehouse.accounts import REDIRECT_FIELD_NAME
from warehouse.accounts.forms import (
    LoginForm,
    ReAuthenticateForm,
    RecoveryCodeAuthenticationForm,
    RegistrationForm,
    RequestPasswordResetForm,
    ResetPasswordForm,
    TOTPAuthenticationForm,
    WebAuthnAuthenticationForm,
)
from warehouse.accounts.interfaces import (
    IGitHubTokenScanningPayloadVerifyService,
    IPasswordBreachedService,
    ITokenService,
    IUserService,
    TokenException,
    TokenExpired,
    TokenInvalid,
    TokenMissing,
    TooManyEmailsAdded,
    TooManyFailedLogins,
)
from warehouse.accounts.models import Email, User
from warehouse.accounts.utils import InvalidTokenLeakRequest, TokenLeakAnalyzer
from warehouse.admin.flags import AdminFlagValue
from warehouse.cache.origin import origin_cache
from warehouse.email import (
    send_added_as_collaborator_email,
    send_collaborator_added_email,
    send_email_verification_email,
    send_password_change_email,
    send_password_reset_email,
)
from warehouse.packaging.models import (
    JournalEntry,
    Project,
    Release,
    Role,
    RoleInvitation,
)
from warehouse.rate_limiting.interfaces import IRateLimiter
from warehouse.utils.http import is_safe_url

USER_ID_INSECURE_COOKIE = "user_id__insecure"


@view_config(context=TooManyFailedLogins, has_translations=True)
def failed_logins(exc, request):
    resp = HTTPTooManyRequests(
        request._(
            "There have been too many unsuccessful login attempts. Try again later."
        ),
        retry_after=exc.resets_in.total_seconds(),
    )

    # TODO: This is kind of gross, but we need it for as long as the legacy
    #       upload API exists and is supported. Once we get rid of that we can
    #       get rid of this as well.
    resp.status = "{} {}".format(resp.status_code, "Too Many Failed Login Attempts")

    return resp


@view_config(context=TooManyEmailsAdded, has_translations=True)
def unverified_emails(exc, request):
    return HTTPTooManyRequests(
        request._(
            "Too many emails have been added to this account without verifying "
            "them. Check your inbox and follow the verification links. (IP: ${ip})",
            mapping={"ip": request.remote_addr},
        ),
        retry_after=exc.resets_in.total_seconds(),
    )


@view_config(
    route_name="accounts.profile",
    context=User,
    renderer="accounts/profile.html",
    decorator=[
        origin_cache(1 * 24 * 60 * 60, stale_if_error=1 * 24 * 60 * 60)  # 1 day each.
    ],
    has_translations=True,
)
def profile(user, request):
    if user.username != request.matchdict.get("username", user.username):
        return HTTPMovedPermanently(request.current_route_path(username=user.username))

    projects = (
        request.db.query(Project)
        .filter(Project.users.contains(user))
        .join(Project.releases)
        .order_by(Release.created.desc())
        .all()
    )

    return {"user": user, "projects": projects}


@view_config(
    route_name="accounts.login",
    renderer="accounts/login.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    has_translations=True,
)
def login(request, redirect_field_name=REDIRECT_FIELD_NAME, _form_class=LoginForm):
    # TODO: Logging in should reset request.user
    # TODO: Configure the login view as the default view for not having
    #       permission to view something.
    if request.authenticated_userid is not None:
        return HTTPSeeOther(request.route_path("manage.projects"))

    user_service = request.find_service(IUserService, context=None)
    breach_service = request.find_service(IPasswordBreachedService, context=None)

    redirect_to = request.POST.get(
        redirect_field_name, request.GET.get(redirect_field_name)
    )

    form = _form_class(
        request.POST,
        request=request,
        user_service=user_service,
        breach_service=breach_service,
        check_password_metrics_tags=["method:auth", "auth_method:login_form"],
    )

    if request.method == "POST":
        if form.validate():
            # Get the user id for the given username.
            username = form.username.data
            userid = user_service.find_userid(username)

            # If the user has enabled two factor authentication.
            if user_service.has_two_factor(userid):
                two_factor_data = {"userid": userid}
                if redirect_to:
                    two_factor_data["redirect_to"] = redirect_to

                token_service = request.find_service(ITokenService, name="two_factor")
                token = token_service.dumps(two_factor_data)

                # Stuff our token in the query and redirect to two-factor page.
                resp = HTTPSeeOther(
                    request.route_path("accounts.two-factor", _query=token)
                )
                return resp
            else:
                # If the user-originating redirection url is not safe, then
                # redirect to the index instead.
                if not redirect_to or not is_safe_url(
                    url=redirect_to, host=request.host
                ):
                    redirect_to = request.route_path("manage.projects")

                # Actually perform the login routine for our user.
                headers = _login_user(request, userid)

                # Now that we're logged in we'll want to redirect the user to
                # either where they were trying to go originally, or to the default
                # view.
                resp = HTTPSeeOther(redirect_to, headers=dict(headers))

                # We'll use this cookie so that client side javascript can
                # Determine the actual user ID (not username, user ID). This is
                # *not* a security sensitive context and it *MUST* not be used
                # where security matters.
                #
                # We'll also hash this value just to avoid leaking the actual User
                # IDs here, even though it really shouldn't matter.
                resp.set_cookie(
                    USER_ID_INSECURE_COOKIE,
                    hashlib.blake2b(
                        str(userid).encode("ascii"), person=b"warehouse.userid"
                    )
                    .hexdigest()
                    .lower(),
                )

            return resp

    return {
        "form": form,
        "redirect": {"field": REDIRECT_FIELD_NAME, "data": redirect_to},
    }


@view_config(
    route_name="accounts.two-factor",
    renderer="accounts/two-factor.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    has_translations=True,
)
def two_factor_and_totp_validate(request, _form_class=TOTPAuthenticationForm):
    if request.authenticated_userid is not None:
        return HTTPSeeOther(request.route_path("manage.projects"))

    try:
        two_factor_data = _get_two_factor_data(request)
    except TokenException:
        request.session.flash(
            request._("Invalid or expired two factor login."), queue="error"
        )
        return HTTPSeeOther(request.route_path("accounts.login"))

    userid = two_factor_data.get("userid")
    redirect_to = two_factor_data.get("redirect_to")

    user_service = request.find_service(IUserService, context=None)

    two_factor_state = {}
    if user_service.has_totp(userid):
        two_factor_state["totp_form"] = _form_class(
            request.POST,
            user_id=userid,
            user_service=user_service,
            check_password_metrics_tags=["method:auth", "auth_method:login_form"],
        )
    if user_service.has_webauthn(userid):
        two_factor_state["has_webauthn"] = True
    if user_service.has_recovery_codes(userid):
        two_factor_state["has_recovery_codes"] = True

    if request.method == "POST":
        form = two_factor_state["totp_form"]
        if form.validate():
            _login_user(request, userid, two_factor_method="totp")
            user_service.update_user(userid, last_totp_value=form.totp_value.data)

            resp = HTTPSeeOther(redirect_to)
            resp.set_cookie(
                USER_ID_INSECURE_COOKIE,
                hashlib.blake2b(str(userid).encode("ascii"), person=b"warehouse.userid")
                .hexdigest()
                .lower(),
            )
            return resp
        else:
            form.totp_value.data = ""

    return two_factor_state


@view_config(
    uses_session=True,
    request_method="GET",
    route_name="accounts.webauthn-authenticate.options",
    renderer="json",
    has_translations=True,
)
def webauthn_authentication_options(request):
    if request.authenticated_userid is not None:
        return {"fail": {"errors": [request._("Already authenticated")]}}

    try:
        two_factor_data = _get_two_factor_data(request)
    except TokenException:
        request.session.flash(
            request._("Invalid or expired two factor login."), queue="error"
        )
        return {"fail": {"errors": [request._("Invalid or expired two factor login.")]}}

    userid = two_factor_data.get("userid")
    user_service = request.find_service(IUserService, context=None)
    return user_service.get_webauthn_assertion_options(
        userid, challenge=request.session.get_webauthn_challenge(), rp_id=request.domain
    )


@view_config(
    require_csrf=True,
    require_methods=False,
    uses_session=True,
    request_method="POST",
    request_param=WebAuthnAuthenticationForm.__params__,
    route_name="accounts.webauthn-authenticate.validate",
    renderer="json",
    has_translations=True,
)
def webauthn_authentication_validate(request):
    if request.authenticated_userid is not None:
        return {"fail": {"errors": ["Already authenticated"]}}

    try:
        two_factor_data = _get_two_factor_data(request)
    except TokenException:
        request.session.flash(
            request._("Invalid or expired two factor login."), queue="error"
        )
        return {"fail": {"errors": [request._("Invalid or expired two factor login.")]}}

    redirect_to = two_factor_data.get("redirect_to")
    userid = two_factor_data.get("userid")

    user_service = request.find_service(IUserService, context=None)
    form = WebAuthnAuthenticationForm(
        **request.POST,
        user_id=userid,
        user_service=user_service,
        challenge=request.session.get_webauthn_challenge(),
        origin=request.host_url,
        rp_id=request.domain,
    )

    request.session.clear_webauthn_challenge()

    if form.validate():
        credential_id, sign_count = form.validated_credential
        webauthn = user_service.get_webauthn_by_credential_id(userid, credential_id)
        webauthn.sign_count = sign_count

        _login_user(request, userid, two_factor_method="webauthn")

        request.response.set_cookie(
            USER_ID_INSECURE_COOKIE,
            hashlib.blake2b(str(userid).encode("ascii"), person=b"warehouse.userid")
            .hexdigest()
            .lower(),
        )
        return {
            "success": request._("Successful WebAuthn assertion"),
            "redirect_to": redirect_to,
        }

    errors = [str(error) for error in form.credential.errors]
    return {"fail": {"errors": errors}}


@view_config(
    route_name="accounts.recovery-code",
    renderer="accounts/recovery-code.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    has_translations=True,
)
def recovery_code(request, _form_class=RecoveryCodeAuthenticationForm):
    if request.authenticated_userid is not None:
        return HTTPSeeOther(request.route_path("manage.projects"))

    try:
        two_factor_data = _get_two_factor_data(request)
    except TokenException:
        request.session.flash(
            request._("Invalid or expired two factor login."), queue="error"
        )
        return HTTPSeeOther(request.route_path("accounts.login"))

    userid = two_factor_data.get("userid")

    user_service = request.find_service(IUserService, context=None)

    form = _form_class(request.POST, user_id=userid, user_service=user_service)

    if request.method == "POST":
        if form.validate():
            _login_user(request, userid, two_factor_method="recovery-code")

            resp = HTTPSeeOther(request.route_path("manage.account"))
            resp.set_cookie(
                USER_ID_INSECURE_COOKIE,
                hashlib.blake2b(str(userid).encode("ascii"), person=b"warehouse.userid")
                .hexdigest()
                .lower(),
            )

            user_service.record_event(
                userid,
                tag="account:recovery_codes:used",
                ip_address=request.remote_addr,
            )

            request.session.flash(
                request._(
                    "Recovery code accepted. The supplied code cannot be used again."
                ),
                queue="success",
            )

            return resp
        else:
            form.recovery_code_value.data = ""

    return {"form": form}


@view_config(
    route_name="accounts.logout",
    renderer="accounts/logout.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    has_translations=True,
)
def logout(request, redirect_field_name=REDIRECT_FIELD_NAME):
    # TODO: Logging out should reset request.user

    redirect_to = request.POST.get(
        redirect_field_name, request.GET.get(redirect_field_name)
    )

    # If the user-originating redirection url is not safe, then redirect to
    # the index instead.
    if not redirect_to or not is_safe_url(url=redirect_to, host=request.host):
        redirect_to = "/"

    # If we're already logged out, then we'll go ahead and issue our redirect right
    # away instead of trying to log a non-existent user out.
    if request.user is None:
        return HTTPSeeOther(redirect_to)

    if request.method == "POST":
        # A POST to the logout view tells us to logout. There's no form to
        # validate here because there's no data. We should be protected against
        # CSRF attacks still because of the CSRF framework, so users will still
        # need a post body that contains the CSRF token.
        headers = forget(request)

        # When crossing an authentication boundary we want to create a new
        # session identifier. We don't want to keep any information in the
        # session when going from authenticated to unauthenticated because
        # user's generally expect that logging out is a destructive action
        # that erases all of their private data. However, if we don't clear the
        # session then another user can use the computer after them, log in to
        # their account, and then gain access to anything sensitive stored in
        # the session for the original user.
        request.session.invalidate()

        # Now that we're logged out we'll want to redirect the user to either
        # where they were originally, or to the default view.
        resp = HTTPSeeOther(redirect_to, headers=dict(headers))

        # Ensure that we delete our user_id__insecure cookie, since the user is
        # no longer logged in.
        resp.delete_cookie(USER_ID_INSECURE_COOKIE)

        return resp

    return {"redirect": {"field": REDIRECT_FIELD_NAME, "data": redirect_to}}


@view_config(
    route_name="accounts.register",
    renderer="accounts/register.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    has_translations=True,
)
def register(request, _form_class=RegistrationForm):
    if request.authenticated_userid is not None:
        return HTTPSeeOther(request.route_path("manage.projects"))

    # Check if the honeypot field has been filled
    if request.method == "POST" and request.POST.get("confirm_form"):
        return HTTPSeeOther(request.route_path("index"))

    if request.flags.enabled(AdminFlagValue.DISALLOW_NEW_USER_REGISTRATION):
        request.session.flash(
            request._(
                "New user registration temporarily disabled. "
                "See https://pypi.org/help#admin-intervention for details."
            ),
            queue="error",
        )
        return HTTPSeeOther(request.route_path("index"))

    user_service = request.find_service(IUserService, context=None)
    breach_service = request.find_service(IPasswordBreachedService, context=None)

    form = _form_class(
        data=request.POST, user_service=user_service, breach_service=breach_service
    )

    if request.method == "POST" and form.validate():
        user = user_service.create_user(
            form.username.data, form.full_name.data, form.new_password.data
        )
        email = user_service.add_email(
            user.id, form.email.data, request.remote_addr, primary=True
        )
        user_service.record_event(
            user.id,
            tag="account:create",
            ip_address=request.remote_addr,
            additional={"email": form.email.data},
        )

        send_email_verification_email(request, (user, email))

        return HTTPSeeOther(
            request.route_path("index"), headers=dict(_login_user(request, user.id))
        )

    return {"form": form}


@view_config(
    route_name="accounts.request-password-reset",
    renderer="accounts/request-password-reset.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    has_translations=True,
)
def request_password_reset(request, _form_class=RequestPasswordResetForm):
    if request.authenticated_userid is not None:
        return HTTPSeeOther(request.route_path("index"))

    user_service = request.find_service(IUserService, context=None)
    form = _form_class(request.POST, user_service=user_service)
    if request.method == "POST" and form.validate():
        user = user_service.get_user_by_username(form.username_or_email.data)
        email = None
        if user is None:
            user = user_service.get_user_by_email(form.username_or_email.data)
            email = first(
                user.emails, key=lambda e: e.email == form.username_or_email.data
            )

        send_password_reset_email(request, (user, email))
        user_service.record_event(
            user.id,
            tag="account:password:reset:request",
            ip_address=request.remote_addr,
        )

        token_service = request.find_service(ITokenService, name="password")
        n_hours = token_service.max_age // 60 // 60
        return {"n_hours": n_hours}

    return {"form": form}


@view_config(
    route_name="accounts.reset-password",
    renderer="accounts/reset-password.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    has_translations=True,
)
def reset_password(request, _form_class=ResetPasswordForm):
    if request.authenticated_userid is not None:
        return HTTPSeeOther(request.route_path("index"))

    user_service = request.find_service(IUserService, context=None)
    breach_service = request.find_service(IPasswordBreachedService, context=None)
    token_service = request.find_service(ITokenService, name="password")

    def _error(message):
        request.session.flash(message, queue="error")
        return HTTPSeeOther(request.route_path("accounts.request-password-reset"))

    try:
        token = request.params.get("token")
        data = token_service.loads(token)
    except TokenExpired:
        return _error(request._("Expired token: request a new password reset link"))
    except TokenInvalid:
        return _error(request._("Invalid token: request a new password reset link"))
    except TokenMissing:
        return _error(request._("Invalid token: no token supplied"))

    # Check whether this token is being used correctly
    if data.get("action") != "password-reset":
        return _error(request._("Invalid token: not a password reset token"))

    # Check whether a user with the given user ID exists
    user = user_service.get_user(uuid.UUID(data.get("user.id")))
    if user is None:
        return _error(request._("Invalid token: user not found"))

    # Check whether the user has logged in since the token was created
    last_login = data.get("user.last_login")
    if str(user.last_login) > last_login:
        # TODO: track and audit this, seems alertable
        return _error(
            request._(
                "Invalid token: user has logged in since this token was requested"
            )
        )

    # Check whether the password has been changed since the token was created
    password_date = data.get("user.password_date")
    if str(user.password_date) > password_date:
        return _error(
            request._(
                "Invalid token: password has already been changed since this "
                "token was requested"
            )
        )

    form = _form_class(
        **request.params,
        username=user.username,
        full_name=user.name,
        email=user.email,
        user_service=user_service,
        breach_service=breach_service,
    )

    if request.method == "POST" and form.validate():
        # Update password.
        user_service.update_user(user.id, password=form.new_password.data)
        user_service.record_event(
            user.id, tag="account:password:reset", ip_address=request.remote_addr
        )

        # Send password change email
        send_password_change_email(request, user)

        # Flash a success message
        request.session.flash(
            request._("You have reset your password"), queue="success"
        )

        # Redirect to account login.
        return HTTPSeeOther(request.route_path("accounts.login"))

    return {"form": form}


@view_config(
    route_name="accounts.verify-email",
    uses_session=True,
    permission="manage:user",
    has_translations=True,
)
def verify_email(request):
    token_service = request.find_service(ITokenService, name="email")
    email_limiter = request.find_service(IRateLimiter, name="email.add")

    def _error(message):
        request.session.flash(message, queue="error")
        return HTTPSeeOther(request.route_path("manage.account"))

    try:
        token = request.params.get("token")
        data = token_service.loads(token)
    except TokenExpired:
        return _error(request._("Expired token: request a new email verification link"))
    except TokenInvalid:
        return _error(request._("Invalid token: request a new email verification link"))
    except TokenMissing:
        return _error(request._("Invalid token: no token supplied"))

    # Check whether this token is being used correctly
    if data.get("action") != "email-verify":
        return _error(request._("Invalid token: not an email verification token"))

    try:
        email = (
            request.db.query(Email)
            .filter(Email.id == data["email.id"], Email.user == request.user)
            .one()
        )
    except NoResultFound:
        return _error(request._("Email not found"))

    if email.verified:
        return _error(request._("Email already verified"))

    email.verified = True
    email.unverify_reason = None
    email.transient_bounces = 0
    email.user.record_event(
        tag="account:email:verified",
        ip_address=request.remote_addr,
        additional={"email": email.email, "primary": email.primary},
    )

    # Reset the email-adding rate limiter for this IP address
    email_limiter.clear(request.remote_addr)

    if not email.primary:
        confirm_message = request._(
            "You can now set this email as your primary address"
        )
    else:
        confirm_message = request._("This is your primary address")

    request.user.is_active = True

    request.session.flash(
        request._(
            "Email address ${email_address} verified. ${confirm_message}.",
            mapping={"email_address": email.email, "confirm_message": confirm_message},
        ),
        queue="success",
    )
    return HTTPSeeOther(request.route_path("manage.account"))


def _get_two_factor_data(request, _redirect_to="/"):
    token_service = request.find_service(ITokenService, name="two_factor")
    two_factor_data, timestamp = token_service.loads(
        request.query_string, return_timestamp=True
    )

    if two_factor_data.get("userid") is None:
        raise TokenInvalid

    user_service = request.find_service(IUserService, context=None)
    user = user_service.get_user(two_factor_data.get("userid"))
    if timestamp < user.last_login:
        raise TokenInvalid

    # If the user-originating redirection url is not safe, then
    # redirect to the index instead.
    redirect_to = two_factor_data.get("redirect_to")
    if redirect_to is None or not is_safe_url(url=redirect_to, host=request.host):
        two_factor_data["redirect_to"] = _redirect_to

    return two_factor_data


@view_config(
    route_name="accounts.verify-project-role",
    renderer="accounts/invite-confirmation.html",
    require_methods=False,
    uses_session=True,
    permission="manage:user",
    has_translations=True,
)
def verify_project_role(request):
    token_service = request.find_service(ITokenService, name="email")
    user_service = request.find_service(IUserService, context=None)

    def _error(message):
        request.session.flash(message, queue="error")
        return HTTPSeeOther(request.route_path("manage.projects"))

    try:
        token = request.params.get("token")
        data = token_service.loads(token)
    except TokenExpired:
        return _error(request._("Expired token: request a new project role invite"))
    except TokenInvalid:
        return _error(request._("Invalid token: request a new project role invite"))
    except TokenMissing:
        return _error(request._("Invalid token: no token supplied"))

    # Check whether this token is being used correctly
    if data.get("action") != "email-project-role-verify":
        return _error(request._("Invalid token: not a collaboration invitation token"))

    user = user_service.get_user(data.get("user_id"))
    if user != request.user:
        return _error(request._("Role invitation is not valid."))

    project = (
        request.db.query(Project).filter(Project.id == data.get("project_id")).one()
    )
    desired_role = data.get("desired_role")

    role_invite = (
        request.db.query(RoleInvitation)
        .filter(RoleInvitation.project == project)
        .filter(RoleInvitation.user == user)
        .one_or_none()
    )

    if not role_invite:
        return _error(request._("Role invitation no longer exists."))

    # Use the renderer to bring up a confirmation page
    # before adding as contributor
    if request.method == "GET":
        return {
            "project_name": project.name,
            "desired_role": desired_role,
        }
    elif request.method == "POST" and "decline" in request.POST:
        request.db.delete(role_invite)
        request.session.flash(
            request._(
                "Invitation for '${project_name}' is declined.",
                mapping={"project_name": project.name},
            ),
            queue="success",
        )
        return HTTPSeeOther(request.route_path("manage.projects"))

    request.db.add(Role(user=user, project=project, role_name=desired_role))
    request.db.delete(role_invite)
    request.db.add(
        JournalEntry(
            name=project.name,
            action=f"accepted {desired_role} {user.username}",
            submitted_by=request.user,
            submitted_from=request.remote_addr,
        )
    )
    project.record_event(
        tag="project:role:accepted",
        ip_address=request.remote_addr,
        additional={
            "submitted_by": request.user.username,
            "role_name": desired_role,
            "target_user": user.username,
        },
    )
    user.record_event(
        tag="account:role:accepted",
        ip_address=request.remote_addr,
        additional={
            "submitted_by": request.user.username,
            "project_name": project.name,
            "role_name": desired_role,
        },
    )

    owner_roles = (
        request.db.query(Role)
        .filter(Role.project == project)
        .filter(Role.role_name == "Owner")
        .all()
    )
    owner_users = {owner.user for owner in owner_roles}

    # Don't send email to new user if they are now an owner
    owner_users.discard(user)

    submitter_user = user_service.get_user(data.get("submitter_id"))
    send_collaborator_added_email(
        request,
        owner_users,
        user=user,
        submitter=submitter_user,
        project_name=project.name,
        role=desired_role,
    )

    send_added_as_collaborator_email(
        request,
        user,
        submitter=submitter_user,
        project_name=project.name,
        role=desired_role,
    )

    request.session.flash(
        request._(
            "You are now ${role} of the '${project_name}' project.",
            mapping={"project_name": project.name, "role": desired_role},
        ),
        queue="success",
    )

    if desired_role == "Owner":
        return HTTPSeeOther(
            request.route_path("manage.project.roles", project_name=project.name)
        )
    else:
        return HTTPSeeOther(request.route_path("packaging.project", name=project.name))


def _login_user(request, userid, two_factor_method=None):
    # We have a session factory associated with this request, so in order
    # to protect against session fixation attacks we're going to make sure
    # that we create a new session (which for sessions with an identifier
    # will cause it to get a new session identifier).

    # We need to protect against session fixation attacks, so make sure
    # that we create a new session (which will cause it to get a new
    # session identifier).
    if (
        request.unauthenticated_userid is not None
        and request.unauthenticated_userid != userid
    ):
        # There is already a userid associated with this request and it is
        # a different userid than the one we're trying to remember now. In
        # this case we want to drop the existing session completely because
        # we don't want to leak any data between authenticated userids.
        request.session.invalidate()
    else:
        # We either do not have an associated userid with this request
        # already, or the userid is the same one we're trying to remember
        # now. In either case we want to keep all of the data but we want
        # to make sure that we create a new session since we're crossing
        # a privilege boundary.
        data = dict(request.session.items())
        request.session.invalidate()
        request.session.update(data)

    # Remember the userid using the authentication policy.
    headers = remember(request, str(userid))

    # Cycle the CSRF token since we've crossed an authentication boundary
    # and we don't want to continue using the old one.
    request.session.new_csrf_token()

    # Whenever we log in the user, we want to update their user so that it
    # records when the last login was.
    user_service = request.find_service(IUserService, context=None)
    user_service.update_user(userid, last_login=datetime.datetime.utcnow())
    user_service.record_event(
        userid,
        tag="account:login:success",
        ip_address=request.remote_addr,
        additional={"two_factor_method": two_factor_method},
    )
    request.session.record_auth_timestamp()
    return headers


@view_config(
    route_name="includes.current-user-profile-callout",
    context=User,
    renderer="includes/accounts/profile-callout.html",
    uses_session=True,
    has_translations=True,
)
def profile_callout(user, request):
    return {"user": user}


@view_config(
    route_name="includes.profile-actions",
    context=User,
    renderer="includes/accounts/profile-actions.html",
    uses_session=True,
    has_translations=True,
)
def edit_profile_button(user, request):
    return {"user": user}


@view_config(
    route_name="includes.profile-public-email",
    context=User,
    renderer="includes/accounts/profile-public-email.html",
    uses_session=True,
    has_translations=True,
)
def profile_public_email(user, request):
    return {"user": user}


@view_config(
    route_name="accounts.reauthenticate",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    has_translations=True,
)
def reauthenticate(request, _form_class=ReAuthenticateForm):
    if request.user is None:
        return HTTPSeeOther(request.route_path("accounts.login"))

    user_service = request.find_service(IUserService, context=None)

    form = _form_class(
        request.POST,
        request=request,
        username=request.user.username,
        next_route=request.matched_route.name,
        next_route_matchdict=json.dumps(request.matchdict),
        user_service=user_service,
        check_password_metrics_tags=[
            "method:reauth",
            "auth_method:reauthenticate_form",
        ],
    )

    if form.next_route.data and form.next_route_matchdict.data:
        redirect_to = request.route_path(
            form.next_route.data, **json.loads(form.next_route_matchdict.data)
        )
    else:
        redirect_to = request.route_path("manage.projects")

    resp = HTTPSeeOther(redirect_to)

    if request.method == "POST" and form.validate():
        request.session.record_auth_timestamp()

    return resp


@view_config(
    require_methods=["POST"],
    require_csrf=False,
    renderer="json",
    route_name="accounts.github-disclose-token",
    header="GITHUB-PUBLIC-KEY-IDENTIFIER",
    # TODO: How to check multiple headers in the predicates ?
    # header="GITHUB-PUBLIC-KEY-SIGNATURE"
    has_translations=True,  # Not the view itself, but the email it sends
)
def github_disclose_token(request):
    # GitHub calls this API view when they have identified a string matching
    # the regular expressions we provided them.
    # Our job is to validate we're talking to github, check if the string contains
    # valid credentials and, if they do, invalidate them and warn the owner

    # The documentation for this process is at
    # https://developer.github.com/partnerships/token-scanning/

    body = request.body

    # Thanks to the predicates, we know the headers we need are defined.
    key_id = request.headers.get("GITHUB-PUBLIC-KEY-IDENTIFIER")
    signature = request.headers.get("GITHUB-PUBLIC-KEY-SIGNATURE")

    verifier = request.find_service(
        IGitHubTokenScanningPayloadVerifyService, context=None
    )

    if not verifier.verify(payload=body, key_id=key_id, signature=signature):
        request.response.status_int = 403
        return {"error": "invalid signature"}

    try:
        disclosures = request.json_body
    except json.decoder.JSONDecodeError:
        request.response.status_int = 400
        return {"error": "body is not valid json"}

    analyzer = TokenLeakAnalyzer(request=request)

    try:
        analyzer.analyze_disclosures(disclosure_records=disclosures, origin="github")
    except InvalidTokenLeakRequest:
        request.response.status_int = 400
        return {"error": "cannot read disclosures from payload"}

    # 204 No Content: we acknowledge but we won't comment on the outcome.#
    return Response(status=204)
