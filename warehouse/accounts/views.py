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

import humanize
import pytz
import sentry_sdk

from first import first
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPMovedPermanently,
    HTTPNotFound,
    HTTPSeeOther,
    HTTPTooManyRequests,
    HTTPUnauthorized,
)
from pyramid.interfaces import ISecurityPolicy
from pyramid.security import forget, remember
from pyramid.view import view_config, view_defaults
from sqlalchemy.exc import NoResultFound
from webauthn.helpers import bytes_to_base64url
from webob.multidict import MultiDict

from warehouse.accounts import REDIRECT_FIELD_NAME
from warehouse.accounts.forms import (
    LoginForm,
    ReAuthenticateForm,
    RecoveryCodeAuthenticationForm,
    RegistrationForm,
    RequestPasswordResetForm,
    ResetPasswordForm,
    TOTPAuthenticationForm,
    UsernameSearchForm,
    WebAuthnAuthenticationForm,
)
from warehouse.accounts.interfaces import (
    IPasswordBreachedService,
    ITokenService,
    IUserService,
    TokenException,
    TokenExpired,
    TokenInvalid,
    TokenMissing,
    TooManyEmailsAdded,
    TooManyFailedLogins,
    TooManyPasswordResetRequests,
)
from warehouse.accounts.models import Email, User
from warehouse.admin.flags import AdminFlagValue
from warehouse.authnz import Permissions
from warehouse.cache.origin import origin_cache
from warehouse.captcha.interfaces import ICaptchaService
from warehouse.email import (
    send_added_as_collaborator_email,
    send_added_as_organization_member_email,
    send_collaborator_added_email,
    send_declined_as_invited_organization_member_email,
    send_email_verification_email,
    send_organization_member_added_email,
    send_organization_member_invite_declined_email,
    send_password_change_email,
    send_password_reset_email,
    send_recovery_code_reminder_email,
)
from warehouse.events.tags import EventTag
from warehouse.metrics.interfaces import IMetricsService
from warehouse.oidc.forms import (
    DeletePublisherForm,
    PendingActiveStatePublisherForm,
    PendingGitHubPublisherForm,
    PendingGitLabPublisherForm,
    PendingGooglePublisherForm,
)
from warehouse.oidc.interfaces import TooManyOIDCRegistrations
from warehouse.oidc.models import (
    PendingActiveStatePublisher,
    PendingGitHubPublisher,
    PendingGitLabPublisher,
    PendingGooglePublisher,
    PendingOIDCPublisher,
)
from warehouse.organizations.interfaces import IOrganizationService
from warehouse.organizations.models import OrganizationRole, OrganizationRoleType
from warehouse.packaging.models import (
    JournalEntry,
    Project,
    ProjectFactory,
    Release,
    Role,
    RoleInvitation,
)
from warehouse.rate_limiting.interfaces import IRateLimiter
from warehouse.utils.http import is_safe_url

USER_ID_INSECURE_COOKIE = "user_id__insecure"
REMEMBER_DEVICE_COOKIE = "remember_device"


@view_config(context=TooManyFailedLogins, has_translations=True)
def failed_logins(exc, request):
    resp = HTTPTooManyRequests(
        request._(
            "There have been too many unsuccessful login attempts. "
            "You have been locked out for {}. "
            "Please try again later.".format(
                humanize.naturaldelta(exc.resets_in.total_seconds())
            )
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


@view_config(context=TooManyPasswordResetRequests, has_translations=True)
def incomplete_password_resets(exc, request):
    return HTTPTooManyRequests(
        request._(
            "Too many password resets have been requested for this account without "
            "completing them. Check your inbox and follow the verification links. "
            "(IP: ${ip})",
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
    route_name="accounts.search",
    renderer="api/account_search.html",
    uses_session=True,
)
def accounts_search(request) -> dict[str, list[User]]:
    """
    Search for usernames based on prefix.
    Used with autocomplete.
    User must be logged in.
    """
    if request.user is None:
        raise HTTPUnauthorized()

    form = UsernameSearchForm(request.params)
    if not form.validate():
        raise HTTPBadRequest()

    search_limiter = request.find_service(IRateLimiter, name="accounts.search")
    if not search_limiter.test(request.ip_address):
        # TODO: This should probably `raise HTTPTooManyRequests` instead,
        #  but we need to make sure that the client library can handle it.
        #  See: https://github.com/afcapel/stimulus-autocomplete/issues/136
        return {"users": []}

    user_service = request.find_service(IUserService, context=None)
    # type guard, see:
    # https://github.com/python/typeshed/pull/10557#issuecomment-1732358909
    assert form.username.data is not None
    users = user_service.get_users_by_prefix(form.username.data.strip())
    search_limiter.hit(request.ip_address)

    if not users:
        raise HTTPNotFound()

    return {"users": users}


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
    if request.user is not None:
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

            # If the user has enabled two-factor authentication and they do not have
            # a valid saved device.
            two_factor_required = user_service.has_two_factor(userid) and (
                not _check_remember_device_token(request, userid)
            )
            if two_factor_required:
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
    # TODO: Using `request.user` here fails `test_totp_auth()` because
    #  of how the test is constructed. We should fix that.
    if request.identity is not None:
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
            request=request,
            user_id=userid,
            user_service=user_service,
            check_password_metrics_tags=["method:auth", "auth_method:login_form"],
        )
    if user_service.has_webauthn(userid):
        two_factor_state["has_webauthn"] = True
    if user_service.has_recovery_codes(userid):
        two_factor_state["has_recovery_codes"] = True
    two_factor_state["remember_device_days"] = request.registry.settings[
        "remember_device.days"
    ]

    if request.method == "POST":
        form = two_factor_state["totp_form"]
        if form.validate():
            two_factor_method = "totp"
            _login_user(request, userid, two_factor_method, two_factor_label="totp")
            user_service.update_user(userid, last_totp_value=form.totp_value.data)

            resp = HTTPSeeOther(redirect_to)
            resp.set_cookie(
                USER_ID_INSECURE_COOKIE,
                hashlib.blake2b(str(userid).encode("ascii"), person=b"warehouse.userid")
                .hexdigest()
                .lower(),
            )

            if not two_factor_state.get("has_recovery_codes", False):
                send_recovery_code_reminder_email(request, request.user)

            if form.remember_device.data:
                _remember_device(request, resp, userid, two_factor_method)

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
    if request.user is not None:
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
    # TODO: Using `request.user` here fails `test_webauthn_validate()` because
    #  of how the test is constructed. We should fix that.
    if request.identity is not None:
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
        request.POST,
        request=request,
        user_id=userid,
        user_service=user_service,
        challenge=request.session.get_webauthn_challenge(),
        origin=request.host_url,
        rp_id=request.domain,
    )

    request.session.clear_webauthn_challenge()

    if form.validate():
        webauthn = user_service.get_webauthn_by_credential_id(
            userid, bytes_to_base64url(form.validated_credential.credential_id)
        )
        webauthn.sign_count = form.validated_credential.new_sign_count

        two_factor_method = "webauthn"
        _login_user(request, userid, two_factor_method, two_factor_label=webauthn.label)

        request.response.set_cookie(
            USER_ID_INSECURE_COOKIE,
            hashlib.blake2b(str(userid).encode("ascii"), person=b"warehouse.userid")
            .hexdigest()
            .lower(),
        )

        if not request.user.has_recovery_codes:
            send_recovery_code_reminder_email(request, request.user)

        if form.remember_device.data:
            _remember_device(request, request.response, userid, two_factor_method)

        return {
            "success": request._("Successful WebAuthn assertion"),
            "redirect_to": redirect_to,
        }

    errors = [str(error) for error in form.credential.errors]
    return {"fail": {"errors": errors}}


def _check_remember_device_token(request, user_id) -> bool:
    """
    Returns true if the given remember device cookie is valid for the given user.
    """
    remember_device_token = request.cookies.get(REMEMBER_DEVICE_COOKIE)
    if not remember_device_token:
        return False
    token_service = request.find_service(ITokenService, name="remember_device")
    try:
        data = token_service.loads(remember_device_token)
        user_id_token = data.get("user_id")
        return user_id_token == str(user_id)
    except TokenException:
        return False


def _remember_device(request, response, userid, two_factor_method) -> None:
    """
    Generates and sets a cookie for remembering this device.
    """
    remember_device_data = {"user_id": str(userid)}
    token_service = request.find_service(ITokenService, name="remember_device")
    token = token_service.dumps(remember_device_data)
    response.set_cookie(
        REMEMBER_DEVICE_COOKIE,
        token,
        max_age=request.registry.settings["remember_device.seconds"],
        httponly=True,
        secure=request.scheme == "https",
        samesite=b"strict",
        path=request.route_path("accounts.login"),
    )
    request.user.record_event(
        tag=EventTag.Account.TwoFactorDeviceRemembered,
        request=request,
        additional={
            "two_factor_method": two_factor_method,
        },
    )


@view_config(
    route_name="accounts.recovery-code",
    renderer="accounts/recovery-code.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    has_translations=True,
)
def recovery_code(request, _form_class=RecoveryCodeAuthenticationForm):
    if request.user is not None:
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

    form = _form_class(
        request.POST, request=request, user_id=userid, user_service=user_service
    )

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

            user = user_service.get_user(userid)
            user.record_event(
                tag=EventTag.Account.RecoveryCodesUsed,
                request=request,
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

        # We've logged the user out, so we want to ensure that we invalid the cache
        # for our security policy, if we're using one that can be reset during login
        security_policy = request.registry.queryUtility(ISecurityPolicy)
        if hasattr(security_policy, "reset"):
            security_policy.reset(request)

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
    if request.user is not None:
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
    captcha_service = request.find_service(ICaptchaService, name="captcha")
    request.find_service(name="csp").merge(captcha_service.csp_policy)

    # the form contains an auto-generated field from recaptcha with
    # hyphens in it. make it play nice with wtforms.
    post_body = MultiDict(
        {key.replace("-", "_"): value for key, value in request.POST.items()}
    )

    form = _form_class(
        request=request,
        formdata=post_body,
        user_service=user_service,
        captcha_service=captcha_service,
        breach_service=breach_service,
    )

    if request.method == "POST" and form.validate():
        email_limiter = request.find_service(IRateLimiter, name="email.verify")
        user = user_service.create_user(
            form.username.data, form.full_name.data, form.new_password.data
        )
        email = user_service.add_email(user.id, form.email.data, primary=True)
        user.record_event(
            tag=EventTag.Account.AccountCreate,
            request=request,
            additional={"email": form.email.data},
        )

        send_email_verification_email(request, (user, email))
        email_limiter.hit(user.id)

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
    if request.user is not None:
        return HTTPSeeOther(request.route_path("index"))

    user_service = request.find_service(IUserService, context=None)
    form = _form_class(request.POST, user_service=user_service)
    if request.method == "POST" and form.validate():
        user = user_service.get_user_by_username(form.username_or_email.data)

        if user is None:
            user = user_service.get_user_by_email(form.username_or_email.data)
        if user is not None:
            email = first(
                user.emails, key=lambda e: e.email == form.username_or_email.data
            )
        else:
            token_service = request.find_service(ITokenService, name="password")
            n_hours = token_service.max_age // 60 // 60
            # We could not find the user by username nor email.
            # Return a response as if we did, to avoid leaking registered emails.
            return {"n_hours": n_hours}

        if not user_service.ratelimiters["password.reset"].test(user.id):
            raise TooManyPasswordResetRequests(
                resets_in=user_service.ratelimiters["password.reset"].resets_in(user.id)
            )

        if user.can_reset_password:
            send_password_reset_email(request, (user, email))
            user.record_event(
                tag=EventTag.Account.PasswordResetRequest,
                request=request,
            )
            user_service.ratelimiters["password.reset"].hit(user.id)

            token_service = request.find_service(ITokenService, name="password")
            n_hours = token_service.max_age // 60 // 60
            return {"n_hours": n_hours}
        else:
            user.record_event(
                tag=EventTag.Account.PasswordResetAttempt,
                request=request,
            )
            request.session.flash(
                request._(
                    (
                        "Automated password reset prohibited for your user. "
                        "Contact a PyPI administrator for assistance"
                    ),
                ),
                queue="error",
            )
            return HTTPSeeOther(request.route_path("accounts.request-password-reset"))

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
    if request.user is not None:
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
    last_login = datetime.datetime.fromisoformat(data.get("user.last_login"))
    # Before updating itsdangerous to 2.x the last_login was naive,
    # now it's localized to UTC
    if not last_login.tzinfo:
        last_login = pytz.UTC.localize(last_login)
    if user.last_login and user.last_login > last_login:
        sentry_sdk.set_context(
            "user",
            {
                "username": user.username,
                "last_login": user.last_login,
                "token_last_login": last_login,
            },
        )
        sentry_sdk.capture_message(
            f"Password reset token used after user logged in for {user.username}",
            level="warning",
        )
        return _error(
            request._(
                "Invalid token: user has logged in since this token was requested"
            )
        )

    # Check whether the password has been changed since the token was created
    password_date = datetime.datetime.fromisoformat(data.get("user.password_date"))
    # Before updating itsdangerous to 2.x the password_date was naive,
    # now it's localized to UTC
    if not password_date.tzinfo:
        password_date = pytz.UTC.localize(password_date)
    current_password_date = (
        user.password_date
        if user.password_date is not None
        else datetime.datetime.min.replace(tzinfo=pytz.UTC)
    )
    if current_password_date > password_date:
        return _error(
            request._(
                "Invalid token: password has already been changed since this "
                "token was requested"
            )
        )

    form = _form_class(
        request.POST,
        username=user.username,
        full_name=user.name,
        email=user.email,
        user_service=user_service,
        breach_service=breach_service,
    )

    if request.method == "POST" and form.validate():
        password_reset_limiter = request.find_service(
            IRateLimiter, name="password.reset"
        )
        # Update password.
        user_service.update_user(user.id, password=form.new_password.data)
        user.record_event(
            tag=EventTag.Account.PasswordReset,
            request=request,
        )
        password_reset_limiter.clear(user.id)

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
    permission=Permissions.AccountVerifyEmail,
    has_translations=True,
)
def verify_email(request):
    token_service = request.find_service(ITokenService, name="email")
    email_limiter = request.find_service(IRateLimiter, name="email.add")
    verify_limiter = request.find_service(IRateLimiter, name="email.verify")

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
            .filter(Email.id == int(data["email.id"]), Email.user == request.user)
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
        tag=EventTag.Account.EmailVerified,
        request=request,
        additional={"email": email.email, "primary": email.primary},
    )

    # Reset the email-adding rate limiter for this IP address
    email_limiter.clear(request.remote_addr)
    # Reset the email verification rate limiter for this User
    verify_limiter.clear(request.user.id)

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

    # If they've already set up a 2FA app, send them to their account page.
    if request.user.has_two_factor:
        return HTTPSeeOther(request.route_path("manage.account"))
    # Otherwise, send them to the two-factor setup page.
    return HTTPSeeOther(request.route_path("manage.account.two-factor"))


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
    route_name="accounts.verify-organization-role",
    renderer="accounts/organization-invite-confirmation.html",
    require_methods=False,
    uses_session=True,
    permission=Permissions.AccountVerifyOrgRole,
    has_translations=True,
)
def verify_organization_role(request):
    token_service = request.find_service(ITokenService, name="email")
    organization_service = request.find_service(IOrganizationService, context=None)
    user_service = request.find_service(IUserService, context=None)

    def _error(message):
        request.session.flash(message, queue="error")
        return HTTPSeeOther(request.route_path("manage.organizations"))

    try:
        token = request.params.get("token")
        data = token_service.loads(token)
    except TokenExpired:
        return _error(request._("Expired token: request a new organization invitation"))
    except TokenInvalid:
        return _error(request._("Invalid token: request a new organization invitation"))
    except TokenMissing:
        return _error(request._("Invalid token: no token supplied"))

    # Check whether this token is being used correctly
    if data.get("action") != "email-organization-role-verify":
        return _error(request._("Invalid token: not an organization invitation token"))

    user = user_service.get_user(data.get("user_id"))
    if user != request.user:
        return _error(request._("Organization invitation is not valid."))

    organization = organization_service.get_organization(data.get("organization_id"))
    desired_role = data.get("desired_role")

    organization_invite = organization_service.get_organization_invite_by_user(
        organization.id, user.id
    )
    if not organization_invite:
        return _error(request._("Organization invitation no longer exists."))

    # Use the renderer to bring up a confirmation page
    # before adding as contributor
    if request.method == "GET":
        return {
            "organization_name": organization.name,
            "desired_role": desired_role,
        }
    elif request.method == "POST" and "decline" in request.POST:
        organization_service.delete_organization_invite(organization_invite.id)
        submitter_user = user_service.get_user(data.get("submitter_id"))
        message = request.params.get("message", "")
        organization.record_event(
            tag=EventTag.Organization.OrganizationRoleDeclineInvite,
            request=request,
            additional={
                "submitted_by_user_id": str(submitter_user.id),
                "role_name": desired_role,
                "target_user_id": str(user.id),
            },
        )
        user.record_event(
            tag=EventTag.Account.OrganizationRoleDeclineInvite,
            request=request,
            additional={
                "submitted_by_user_id": str(submitter_user.id),
                "organization_name": organization.name,
                "role_name": desired_role,
            },
        )
        owner_roles = (
            request.db.query(OrganizationRole)
            .filter(OrganizationRole.organization == organization)
            .filter(OrganizationRole.role_name == OrganizationRoleType.Owner)
            .all()
        )
        owner_users = {owner.user for owner in owner_roles}
        send_organization_member_invite_declined_email(
            request,
            owner_users,
            user=user,
            organization_name=organization.name,
            message=message,
        )
        send_declined_as_invited_organization_member_email(
            request,
            user,
            organization_name=organization.name,
        )
        request.session.flash(
            request._(
                "Invitation for '${organization_name}' is declined.",
                mapping={"organization_name": organization.name},
            ),
            queue="success",
        )
        return HTTPSeeOther(request.route_path("manage.organizations"))

    organization_service.add_organization_role(
        organization_id=organization.id,
        user_id=user.id,
        role_name=desired_role,
    )
    organization_service.delete_organization_invite(organization_invite.id)
    submitter_user = user_service.get_user(data.get("submitter_id"))
    organization.record_event(
        tag=EventTag.Organization.OrganizationRoleAdd,
        request=request,
        additional={
            "submitted_by_user_id": str(submitter_user.id),
            "role_name": desired_role,
            "target_user_id": str(user.id),
        },
    )
    user.record_event(
        tag=EventTag.Account.OrganizationRoleAdd,
        request=request,
        additional={
            "submitted_by_user_id": str(submitter_user.id),
            "organization_name": organization.name,
            "role_name": desired_role,
        },
    )

    owner_roles = (
        request.db.query(OrganizationRole)
        .filter(OrganizationRole.organization == organization)
        .filter(OrganizationRole.role_name == OrganizationRoleType.Owner)
        .all()
    )
    owner_users = {owner.user for owner in owner_roles}

    # Don't send email to new user if they are now an owner
    owner_users.discard(user)

    send_organization_member_added_email(
        request,
        owner_users,
        user=user,
        submitter=submitter_user,
        organization_name=organization.name,
        role=desired_role,
    )

    send_added_as_organization_member_email(
        request,
        user,
        submitter=submitter_user,
        organization_name=organization.name,
        role=desired_role,
    )

    request.session.flash(
        request._(
            "You are now ${role} of the '${organization_name}' organization.",
            mapping={"organization_name": organization.name, "role": desired_role},
        ),
        queue="success",
    )

    return HTTPSeeOther(
        request.route_path(
            "manage.organization.roles", organization_name=organization.normalized_name
        )
    )


@view_config(
    route_name="accounts.verify-project-role",
    renderer="accounts/invite-confirmation.html",
    require_methods=False,
    uses_session=True,
    permission=Permissions.AccountVerifyProjectRole,
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
        return _error(request._("Expired token: request a new project role invitation"))
    except TokenInvalid:
        return _error(request._("Invalid token: request a new project role invitation"))
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
        submitter_user = user_service.get_user(data.get("submitter_id"))
        project.record_event(
            tag=EventTag.Project.RoleDeclineInvite,
            request=request,
            additional={
                "submitted_by": submitter_user.username,
                "role_name": desired_role,
                "target_user": user.username,
            },
        )
        user.record_event(
            tag=EventTag.Account.RoleDeclineInvite,
            request=request,
            additional={
                "submitted_by": submitter_user.username,
                "project_name": project.name,
                "role_name": desired_role,
            },
        )
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
        )
    )
    project.record_event(
        tag=EventTag.Project.RoleAdd,
        request=request,
        additional={
            "submitted_by": request.user.username,
            "role_name": desired_role,
            "target_user": user.username,
        },
    )
    user.record_event(
        tag=EventTag.Account.RoleAdd,
        request=request,
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


def _login_user(request, userid, two_factor_method=None, two_factor_label=None):
    # We have a session factory associated with this request, so in order
    # to protect against session fixation attacks we're going to make sure
    # that we create a new session (which for sessions with an identifier
    # will cause it to get a new session identifier).

    # We need to protect against session fixation attacks, so make sure
    # that we create a new session (which will cause it to get a new
    # session identifier).
    if (
        request._unauthenticated_userid is not None
        and request._unauthenticated_userid != userid
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

    # We've logged the user in, so we want to ensure that we invalid the cache
    # for our security policy, if we're using one that can be reset during login
    security_policy = request.registry.queryUtility(ISecurityPolicy)
    if hasattr(security_policy, "reset"):
        security_policy.reset(request)

    # Remember the userid using the authentication policy.
    headers = remember(request, str(userid))

    # Cycle the CSRF token since we've crossed an authentication boundary
    # and we don't want to continue using the old one.
    request.session.new_csrf_token()

    # Whenever we log in the user, we want to update their user so that it
    # records when the last login was.
    user_service = request.find_service(IUserService, context=None)
    user_service.update_user(userid, last_login=datetime.datetime.now(datetime.UTC))
    user = user_service.get_user(userid)
    user.record_event(
        tag=EventTag.Account.LoginSuccess,
        request=request,
        additional={
            "two_factor_method": two_factor_method,
            "two_factor_label": two_factor_label,
        },
    )
    request.session.record_auth_timestamp()
    request.session.record_password_timestamp(
        user_service.get_password_timestamp(userid)
    )
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
        next_route_query=json.dumps(request.GET.mixed()),
        user_service=user_service,
        action="reauthenticate",
        check_password_metrics_tags=[
            "method:reauth",
            "auth_method:reauthenticate_form",
        ],
    )

    if form.next_route.data and form.next_route_matchdict.data:
        redirect_to = request.route_path(
            form.next_route.data,
            **json.loads(form.next_route_matchdict.data)
            | dict(_query=json.loads(form.next_route_query.data)),
        )
    else:
        redirect_to = request.route_path("manage.projects")

    resp = HTTPSeeOther(redirect_to)

    if request.method == "POST" and form.validate():
        request.session.record_auth_timestamp()
        request.session.record_password_timestamp(
            user_service.get_password_timestamp(request.user.id)
        )

    return resp


@view_defaults(
    route_name="manage.account.publishing",
    renderer="manage/account/publishing.html",
    uses_session=True,
    require_csrf=True,
    require_methods=False,
    permission=Permissions.AccountManagePublishing,
    has_translations=True,
    require_reauth=True,
)
class ManageAccountPublishingViews:
    def __init__(self, request):
        self.request = request
        self.project_factory = ProjectFactory(request)
        self.metrics = self.request.find_service(IMetricsService, context=None)
        self.pending_github_publisher_form = PendingGitHubPublisherForm(
            self.request.POST,
            api_token=self.request.registry.settings.get("github.token"),
            project_factory=self.project_factory,
        )
        self.pending_gitlab_publisher_form = PendingGitLabPublisherForm(
            self.request.POST,
            project_factory=self.project_factory,
        )
        self.pending_google_publisher_form = PendingGooglePublisherForm(
            self.request.POST,
            project_factory=self.project_factory,
        )
        self.pending_activestate_publisher_form = PendingActiveStatePublisherForm(
            self.request.POST,
            project_factory=self.project_factory,
        )

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
    def default_response(self):
        return {
            "pending_github_publisher_form": self.pending_github_publisher_form,
            "pending_gitlab_publisher_form": self.pending_gitlab_publisher_form,
            "pending_google_publisher_form": self.pending_google_publisher_form,
            "pending_activestate_publisher_form": self.pending_activestate_publisher_form,  # noqa: E501
            "disabled": {
                "GitHub": self.request.flags.disallow_oidc(
                    AdminFlagValue.DISALLOW_GITHUB_OIDC
                ),
                "GitLab": self.request.flags.disallow_oidc(
                    AdminFlagValue.DISALLOW_GITLAB_OIDC
                ),
                "Google": self.request.flags.disallow_oidc(
                    AdminFlagValue.DISALLOW_GOOGLE_OIDC
                ),
                "ActiveState": self.request.flags.disallow_oidc(
                    AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC
                ),
            },
        }

    @view_config(request_method="GET")
    def manage_publishing(self):
        if self.request.flags.disallow_oidc():
            self.request.session.flash(
                self.request._(
                    "Trusted publishing is temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )
            return self.default_response

        return self.default_response

    def _add_pending_oidc_publisher(
        self,
        publisher_name,
        publisher_class,
        admin_flag,
        form,
        make_pending_publisher,
        make_existence_filters,
    ):
        if self.request.flags.disallow_oidc(admin_flag):
            self.request.session.flash(
                self.request._(
                    f"{publisher_name}-based trusted publishing is temporarily "
                    "disabled. See https://pypi.org/help#admin-intervention for "
                    "details."
                ),
                queue="error",
            )
            return self.default_response

        self.metrics.increment(
            "warehouse.oidc.add_pending_publisher.attempt",
            tags=[f"publisher:{publisher_name}"],
        )

        if not self.request.user.has_primary_verified_email:
            self.request.session.flash(
                self.request._(
                    "You must have a verified email in order to register a "
                    "pending trusted publisher. "
                    "See https://pypi.org/help#openid-connect for details."
                ),
                queue="error",
            )
            return self.default_response

        # Separately from having permission to register pending OIDC publishers,
        # we limit users to no more than 3 pending publishers at once.
        if len(self.request.user.pending_oidc_publishers) >= 3:
            self.request.session.flash(
                self.request._(
                    "You can't register more than 3 pending trusted "
                    "publishers at once."
                ),
                queue="error",
            )
            return self.default_response

        try:
            self._check_ratelimits()
        except TooManyOIDCRegistrations as exc:
            self.metrics.increment(
                "warehouse.oidc.add_pending_publisher.ratelimited",
                tags=[f"publisher:{publisher_name}"],
            )
            return HTTPTooManyRequests(
                self.request._(
                    "There have been too many attempted trusted publisher "
                    "registrations. Try again later."
                ),
                retry_after=exc.resets_in.total_seconds(),
            )

        self._hit_ratelimits()

        if not form.validate():
            self.request.session.flash(
                self.request._("The trusted publisher could not be registered"),
                queue="error",
            )
            return self.default_response

        publisher_already_exists = (
            self.request.db.query(publisher_class)
            .filter_by(**make_existence_filters(form))
            .first()
            is not None
        )

        if publisher_already_exists:
            self.request.session.flash(
                self.request._(
                    "This trusted publisher has already been registered. "
                    "Please contact PyPI's admins if this wasn't intentional."
                ),
                queue="error",
            )
            return self.default_response

        pending_publisher = make_pending_publisher(self.request, form)

        self.request.db.add(pending_publisher)
        self.request.db.flush()  # To get the new ID

        self.request.user.record_event(
            tag=EventTag.Account.PendingOIDCPublisherAdded,
            request=self.request,
            additional={
                "project": pending_publisher.project_name,
                "publisher": pending_publisher.publisher_name,
                "id": str(pending_publisher.id),
                "specifier": str(pending_publisher),
                "url": pending_publisher.publisher_url(),
                "submitted_by": self.request.user.username,
            },
        )

        self.request.session.flash(
            self.request._(
                "Registered a new pending publisher to create "
                f"the project '{pending_publisher.project_name}'."
            ),
            queue="success",
        )

        self.metrics.increment(
            "warehouse.oidc.add_pending_publisher.ok",
            tags=[f"publisher:{publisher_name}"],
        )

        return HTTPSeeOther(self.request.path)

    @view_config(
        request_method="POST",
        request_param=PendingGooglePublisherForm.__params__,
    )
    def add_pending_google_oidc_publisher(self):
        form = self.default_response["pending_google_publisher_form"]
        return self._add_pending_oidc_publisher(
            publisher_name="Google",
            publisher_class=PendingGooglePublisher,
            admin_flag=AdminFlagValue.DISALLOW_GOOGLE_OIDC,
            form=form,
            make_pending_publisher=lambda request, form: PendingGooglePublisher(
                project_name=form.project_name.data,
                added_by=request.user,
                email=form.email.data,
                sub=form.sub.data,
            ),
            make_existence_filters=lambda form: dict(
                email=form.email.data,
                sub=form.sub.data,
            ),
        )

    @view_config(
        request_method="POST",
        request_param=PendingGitHubPublisherForm.__params__,
    )
    def add_pending_github_oidc_publisher(self):
        form = self.default_response["pending_github_publisher_form"]
        return self._add_pending_oidc_publisher(
            publisher_name="GitHub",
            publisher_class=PendingGitHubPublisher,
            admin_flag=AdminFlagValue.DISALLOW_GITHUB_OIDC,
            form=form,
            make_pending_publisher=lambda request, form: PendingGitHubPublisher(
                project_name=form.project_name.data,
                added_by=self.request.user,
                repository_name=form.repository.data,
                repository_owner=form.normalized_owner,
                repository_owner_id=form.owner_id,
                workflow_filename=form.workflow_filename.data,
                environment=form.normalized_environment,
            ),
            make_existence_filters=lambda form: dict(
                repository_name=form.repository.data,
                repository_owner=form.normalized_owner,
                workflow_filename=form.workflow_filename.data,
                environment=form.normalized_environment,
            ),
        )

    @view_config(
        request_method="POST",
        request_param=PendingActiveStatePublisherForm.__params__,
    )
    def add_pending_activestate_oidc_publisher(self):
        form = self.default_response["pending_activestate_publisher_form"]
        return self._add_pending_oidc_publisher(
            publisher_name="ActiveState",
            publisher_class=PendingActiveStatePublisher,
            admin_flag=AdminFlagValue.DISALLOW_ACTIVESTATE_OIDC,
            form=form,
            make_pending_publisher=lambda request, form: PendingActiveStatePublisher(
                project_name=form.project_name.data,
                added_by=self.request.user,
                organization=form.organization.data,
                activestate_project_name=form.project.data,
                actor=form.actor.data,
                actor_id=form.actor_id,
            ),
            make_existence_filters=lambda form: dict(
                organization=form.organization.data,
                activestate_project_name=form.project.data,
                actor_id=form.actor_id,
            ),
        )

    @view_config(
        request_method="POST",
        request_param=PendingGitLabPublisherForm.__params__,
    )
    def add_pending_gitlab_oidc_publisher(self):
        form = self.default_response["pending_gitlab_publisher_form"]
        return self._add_pending_oidc_publisher(
            publisher_name="GitLab",
            publisher_class=PendingGitLabPublisher,
            admin_flag=AdminFlagValue.DISALLOW_GITLAB_OIDC,
            form=form,
            make_pending_publisher=lambda request, form: PendingGitLabPublisher(
                project_name=form.project_name.data,
                added_by=self.request.user,
                namespace=form.namespace.data,
                project=form.project.data,
                workflow_filepath=form.workflow_filepath.data,
                environment=form.normalized_environment,
            ),
            make_existence_filters=lambda form: dict(
                namespace=form.namespace.data,
                project=form.project.data,
                workflow_filepath=form.workflow_filepath.data,
                environment=form.normalized_environment,
            ),
        )

    @view_config(
        request_method="POST",
        request_param=DeletePublisherForm.__params__,
    )
    def delete_pending_oidc_publisher(self):
        if self.request.flags.disallow_oidc():
            self.request.session.flash(
                self.request._(
                    "Trusted publishing is temporarily disabled. "
                    "See https://pypi.org/help#admin-intervention for details."
                ),
                queue="error",
            )
            return self.default_response

        self.metrics.increment("warehouse.oidc.delete_pending_publisher.attempt")

        form = DeletePublisherForm(self.request.POST)

        if not form.validate():
            self.request.session.flash(
                self.request._("Invalid publisher ID"),
                queue="error",
            )
            return self.default_response

        pending_publisher = self.request.db.get(
            PendingOIDCPublisher, form.publisher_id.data
        )

        # pending_publisher will be `None` here if someone manually
        # futzes with the form.
        if pending_publisher is None:
            self.request.session.flash(
                self.request._("Invalid publisher ID"),
                queue="error",
            )
            return self.default_response

        if pending_publisher.added_by != self.request.user:
            self.request.session.flash(
                self.request._("Invalid publisher ID"),
                queue="error",
            )
            return self.default_response

        self.request.session.flash(
            self.request._(
                "Removed trusted publisher for project "
                f"{pending_publisher.project_name!r}"
            ),
            queue="success",
        )

        self.metrics.increment(
            "warehouse.oidc.delete_pending_publisher.ok",
            tags=[f"publisher:{pending_publisher.publisher_name}"],
        )

        self.request.user.record_event(
            tag=EventTag.Account.PendingOIDCPublisherRemoved,
            request=self.request,
            additional={
                "project": pending_publisher.project_name,
                "publisher": pending_publisher.publisher_name,
                "id": str(pending_publisher.id),
                "specifier": str(pending_publisher),
                "url": pending_publisher.publisher_url(),
                "submitted_by": self.request.user.username,
            },
        )

        self.request.db.delete(pending_publisher)

        return HTTPSeeOther(self.request.path)
