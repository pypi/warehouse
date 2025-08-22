# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import contextlib
import json
import re

import disposable_email_domains
import dns.resolver
import email_validator
import humanize
import markupsafe
import wtforms
import wtforms.fields

from sqlalchemy import exists
from tldextract import TLDExtract

import warehouse.utils.otp as otp
import warehouse.utils.webauthn as webauthn

from warehouse import forms
from warehouse.accounts.interfaces import (
    BurnedRecoveryCode,
    InvalidRecoveryCode,
    NoRecoveryCodes,
    TooManyFailedLogins,
)
from warehouse.accounts.models import DisableReason, ProhibitedEmailDomain
from warehouse.accounts.services import RECOVERY_CODE_BYTES
from warehouse.captcha import recaptcha
from warehouse.constants import MAX_PASSWORD_SIZE
from warehouse.email import (
    send_password_compromised_email_hibp,
    send_recovery_code_used_email,
)
from warehouse.events.tags import EventTag
from warehouse.i18n import localize as _

# Common messages, set as constants to keep them from drifting.
INVALID_EMAIL_MESSAGE = _("The email address isn't valid. Try again.")
INVALID_PASSWORD_MESSAGE = _("The password is invalid. Try again.")
INVALID_USERNAME_MESSAGE = _(
    "The username is invalid. Usernames "
    "must be composed of letters, numbers, "
    "dots, hyphens and underscores. And must "
    "also start and finish with a letter or number. "
    "Choose a different username."
)


class PreventNullBytesValidator:
    """
    Validation if field contains a null byte.
    Use after `InputRequired()` but before other validators to prevent
    sending null bytes to the database, which would result in `psycopg.DataError`
    """

    def __init__(self, message=None):
        if message is None:
            message = _("Null bytes are not allowed.")
        self.message = message

    def __call__(self, form, field):
        if field.data and "\x00" in field.data:
            raise wtforms.validators.StopValidation(self.message)


def _check_for_existing_username(form: LoginForm, field):
    field.data = field.data.strip()

    userid = form.user_service.find_userid(field.data)

    if userid is None:
        raise wtforms.validators.ValidationError(_("No user found with that username"))


class UsernameMixin:
    username = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(),
            PreventNullBytesValidator(),
            _check_for_existing_username,
        ],
    )


class TOTPValueMixin:
    totp_value = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(),
            PreventNullBytesValidator(),
            wtforms.validators.Regexp(
                rf"^ *([0-9] *){{{otp.TOTP_LENGTH}}}$",
                message=_(
                    "TOTP code must be ${totp_length} digits.",
                    mapping={"totp_length": otp.TOTP_LENGTH},
                ),
            ),
        ]
    )


class WebAuthnCredentialMixin:
    credential = wtforms.StringField(validators=[wtforms.validators.InputRequired()])


class RecoveryCodeValueMixin:
    recovery_code_value = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(),
            PreventNullBytesValidator(),
            wtforms.validators.Regexp(
                rf"^ *([0-9a-f] *){{{2 * RECOVERY_CODE_BYTES}}}$",
                message=_(
                    "Recovery Codes must be ${recovery_code_length} characters.",
                    mapping={"recovery_code_length": 2 * RECOVERY_CODE_BYTES},
                ),
            ),
        ]
    )


class NewUsernameMixin:
    username = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(),
            PreventNullBytesValidator(message=INVALID_USERNAME_MESSAGE),
            wtforms.validators.Length(
                max=50, message=_("Choose a username with 50 characters or less.")
            ),
            # the regexp below must match the CheckConstraint
            # for the username field in accounts.models.User
            wtforms.validators.Regexp(
                r"^[a-zA-Z0-9][a-zA-Z0-9._-]*[a-zA-Z0-9]$",
                message=INVALID_USERNAME_MESSAGE,
            ),
        ]
    )

    def validate_username(self, field):
        if (
            self.user_service.username_is_prohibited(field.data)
            or self.user_service.find_userid(field.data) is not None
        ):
            raise wtforms.validators.ValidationError(
                _(
                    "This username is already being used by another "
                    "account. Choose a different username."
                )
            )


class PasswordMixin:
    password = wtforms.PasswordField(
        validators=[
            wtforms.validators.InputRequired(),
            PreventNullBytesValidator(message=INVALID_PASSWORD_MESSAGE),
            wtforms.validators.Length(
                max=MAX_PASSWORD_SIZE,
                message=_("Password too long."),
            ),
        ]
    )

    def __init__(
        self, *args, request, action="login", check_password_metrics_tags=None, **kwargs
    ):
        self.request = request
        self.action = action
        self._check_password_metrics_tags = check_password_metrics_tags
        super().__init__(*args, **kwargs)

    def validate_password(self, field):
        userid = self.user_service.find_userid(self.username.data)
        if userid is not None:
            try:
                if not self.user_service.check_password(
                    userid,
                    field.data,
                    tags=self._check_password_metrics_tags,
                ):
                    user = self.user_service.get_user(userid)
                    user.record_event(
                        tag=f"account:{self.action}:failure",
                        request=self.request,
                        additional={"reason": "invalid_password"},
                    )
                    raise wtforms.validators.ValidationError(INVALID_PASSWORD_MESSAGE)
            except TooManyFailedLogins as err:
                raise wtforms.validators.ValidationError(
                    _(
                        "There have been too many unsuccessful login attempts. "
                        "You have been locked out for ${time}. "
                        "Please try again later.",
                        mapping={
                            "time": humanize.naturaldelta(err.resets_in.total_seconds())
                        },
                    )
                ) from None


class NewPasswordMixin:
    new_password = wtforms.PasswordField(
        validators=[
            wtforms.validators.InputRequired(),
            PreventNullBytesValidator(message=INVALID_PASSWORD_MESSAGE),
            wtforms.validators.Length(
                max=MAX_PASSWORD_SIZE,
                message=_("Password too long."),
            ),
            forms.PasswordStrengthValidator(
                user_input_fields=["full_name", "username", "email"]
            ),
        ],
    )

    password_confirm = wtforms.PasswordField(
        validators=[
            wtforms.validators.InputRequired(),
            wtforms.validators.Length(
                max=MAX_PASSWORD_SIZE,
                message=_("Password too long."),
            ),
            wtforms.validators.EqualTo(
                "new_password", message=_("Your passwords don't match. Try again.")
            ),
        ],
    )

    # These fields are here to provide the various user-defined fields to the
    # PasswordStrengthValidator of the new_password field, to ensure that the
    # newly set password doesn't contain any of them
    # NOTE: These intentionally use `DataRequired` instead of `InputRequired`,
    # since they may not be form inputs (i.e., they may be precomputed).
    full_name = wtforms.StringField()  # May be empty
    username = wtforms.StringField(validators=[wtforms.validators.DataRequired()])
    email = wtforms.StringField(validators=[wtforms.validators.DataRequired()])

    def __init__(self, *args, breach_service, **kwargs):
        super().__init__(*args, **kwargs)
        self._breach_service = breach_service

    def validate_new_password(self, field):
        if self._breach_service.check_password(
            field.data, tags=["method:new_password"]
        ):
            raise wtforms.validators.ValidationError(
                markupsafe.Markup(self._breach_service.failure_message)
            )


class NewEmailMixin:
    email = wtforms.fields.EmailField(
        validators=[
            wtforms.validators.InputRequired(),
            PreventNullBytesValidator(),
            wtforms.validators.Email(),
            wtforms.validators.Length(
                max=254, message=_("The email address is too long. Try again.")
            ),
        ]
    )

    def __init__(self, *args, request, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)

    def validate_email(self, field):
        # Additional checks for the validity of the address
        try:
            resp = email_validator.validate_email(field.data, check_deliverability=True)
        except email_validator.EmailNotValidError as e:
            self.request.metrics.increment(
                "warehouse.accounts.forms.validate_email",
                tags=["result:invalid", "reason:email_validator"],
            )
            raise wtforms.validators.ValidationError(
                self.request._("The email address isn't valid. Try again.")
            ) from e

        # Check if the domain is valid
        extractor = TLDExtract(suffix_list_urls=())  # Updated during image build
        domain = extractor(resp.domain.lower()).top_domain_under_public_suffix

        mx_domains = set()
        if hasattr(resp, "mx") and resp.mx:
            mx_domains = {
                extractor(mx_host.lower()).top_domain_under_public_suffix
                for _prio, mx_host in resp.mx
            }
            mx_domains.update({mx_host.lower() for _prio, mx_host in resp.mx})

        # Resolve the returned MX domain's IP address to a PTR record, to a domain
        all_mx_domains = set()
        for mx_domain in mx_domains:
            with contextlib.suppress(
                dns.resolver.NoAnswer,
                dns.resolver.NXDOMAIN,
                dns.resolver.NoNameservers,
                dns.resolver.LifetimeTimeout,
            ):
                mx_ip = dns.resolver.resolve(mx_domain, "A")
                mx_ptr = dns.resolver.resolve_address(mx_ip[0].address)
                mx_ptr_domain = extractor(
                    mx_ptr[0].target.to_text().lower()
                ).top_domain_under_public_suffix
                all_mx_domains.add(mx_ptr_domain)

        # combine both sets
        all_mx_domains.update(mx_domains)

        if (
            domain in disposable_email_domains.blocklist
            or self.request.db.query(
                exists().where(
                    (ProhibitedEmailDomain.domain == domain)
                    & (ProhibitedEmailDomain.is_mx_record == False)  # noqa: E712
                )
                | exists().where(
                    (ProhibitedEmailDomain.domain.in_(all_mx_domains))
                    & (ProhibitedEmailDomain.is_mx_record == True)  # noqa: E712
                )
            ).scalar()
        ):
            self.request.metrics.increment(
                "warehouse.accounts.forms.validate_email",
                tags=["result:invalid", "reason:prohibited_domain"],
            )
            raise wtforms.validators.ValidationError(
                self.request._(
                    "You can't use an email address from this domain. Use a "
                    "different email."
                )
            )

        # Check if this email address is already in use
        userid = self.user_service.find_userid_by_email(field.data)

        if userid and userid == self.user_id:
            self.request.metrics.increment(
                "warehouse.accounts.forms.validate_email",
                tags=["result:invalid", "reason:email_in_use_by_self"],
            )
            raise wtforms.validators.ValidationError(
                self.request._(
                    "This email address is already being used by this account. "
                    "Use a different email."
                )
            )
        if userid:
            self.request.metrics.increment(
                "warehouse.accounts.forms.validate_email",
                tags=["result:invalid", "reason:email_in_use_by_other"],
            )
            raise wtforms.validators.ValidationError(
                self.request._(
                    "This email address is already being used "
                    "by another account. Use a different email."
                )
            )

        self.request.metrics.increment(
            "warehouse.accounts.forms.validate_email",
            tags=["result:valid"],
        )


class HoneypotMixin:
    """A mixin to catch spammers. This field should always be blank"""

    confirm_form = wtforms.StringField()


class UsernameSearchForm(wtforms.Form):
    username = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(),
            PreventNullBytesValidator(),
        ],
    )


class RegistrationForm(  # type: ignore[misc]
    # Both `NewEmailMixin` and `NewPasswordMixin` declare an `email` field,
    # we ignore the difference in implementation.
    NewUsernameMixin,
    NewEmailMixin,
    NewPasswordMixin,
    HoneypotMixin,
    wtforms.Form,
):
    full_name = wtforms.StringField(
        validators=[
            wtforms.validators.Length(
                max=100,
                message=_(
                    "The name is too long. "
                    "Choose a name with 100 characters or less."
                ),
            ),
            wtforms.validators.Regexp(
                r"(?i)(?:(?!:\/\/).)*$",
                message=_("URLs are not allowed in the name field."),
            ),
            PreventNullBytesValidator(),
        ]
    )
    captcha_response = wtforms.StringField()

    def __init__(self, *args, captcha_service, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service
        self.user_id = None
        self.captcha_service = captcha_service

    def validate_captcha_response(self, field):
        # do required data validation here due to enabled flag being required
        if self.captcha_service.enabled and not field.data:
            raise wtforms.validators.ValidationError("Recaptcha error.")
        try:
            self.captcha_service.verify_response(field.data)
        except recaptcha.RecaptchaError:
            # TODO: log error
            # don't want to provide the user with any detail
            raise wtforms.validators.ValidationError("Recaptcha error.")


class LoginForm(PasswordMixin, UsernameMixin, wtforms.Form):
    def __init__(self, *args, user_service, breach_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service
        self.breach_service = breach_service

    def validate_password(self, field):
        # Before we try to validate anything, first check to see if the IP is banned
        if self.request.banned.by_ip(self.request.remote_addr):
            raise wtforms.validators.ValidationError(INVALID_PASSWORD_MESSAGE)

        # Do our typical validation of the password.
        super().validate_password(field)

        userid = self.user_service.find_userid(self.username.data)

        # If we have a user ID, then we'll go and check it against our breached password
        # service. If the password has appeared in a breach or is otherwise compromised
        # we will disable the user and reject the login.
        if userid is not None:
            # Now we'll check to see if the user is disabled.
            is_disabled, disabled_for = self.user_service.is_disabled(userid)
            if is_disabled and disabled_for == DisableReason.CompromisedPassword:
                raise wtforms.validators.ValidationError(
                    markupsafe.Markup(self.breach_service.failure_message)
                )
            if self.breach_service.check_password(
                field.data, tags=["method:auth", "auth_method:login_form"]
            ):
                user = self.user_service.get_user(userid)
                send_password_compromised_email_hibp(self.request, user)
                self.user_service.disable_password(
                    user.id,
                    self.request,
                    reason=DisableReason.CompromisedPassword,
                )
                raise wtforms.validators.ValidationError(
                    markupsafe.Markup(self.breach_service.failure_message)
                )


class _TwoFactorAuthenticationForm(wtforms.Form):
    def __init__(self, *args, request, user_id, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.user_id = user_id
        self.user_service = user_service

    remember_device = wtforms.BooleanField(default=False)


class TOTPAuthenticationForm(TOTPValueMixin, _TwoFactorAuthenticationForm):
    def validate_totp_value(self, field):
        totp_value = field.data.replace(" ", "").encode("utf8")

        try:
            self.user_service.check_totp_value(self.user_id, totp_value)
        except (otp.InvalidTOTPError, otp.OutOfSyncTOTPError):
            user = self.user_service.get_user(self.user_id)
            user.record_event(
                tag=EventTag.Account.LoginFailure,
                request=self.request,
                additional={"reason": "invalid_totp"},
            )
            raise wtforms.validators.ValidationError(_("Invalid TOTP code."))


class WebAuthnAuthenticationForm(WebAuthnCredentialMixin, _TwoFactorAuthenticationForm):
    __params__ = ["credential"]

    def __init__(self, *args, challenge, origin, rp_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.challenge = challenge
        self.origin = origin
        self.rp_id = rp_id

    def validate_credential(self, field):
        try:
            json.loads(field.data.encode("utf8"))
        except json.JSONDecodeError:
            raise wtforms.validators.ValidationError(
                _("Invalid WebAuthn assertion: Bad payload")
            )

        try:
            validated_credential = self.user_service.verify_webauthn_assertion(
                self.user_id,
                field.data.encode("utf8"),
                challenge=self.challenge,
                origin=self.origin,
                rp_id=self.rp_id,
            )

        except webauthn.AuthenticationRejectedError as e:
            user = self.user_service.get_user(self.user_id)
            user.record_event(
                tag=EventTag.Account.LoginFailure,
                request=self.request,
                additional={"reason": "invalid_webauthn"},
            )
            raise wtforms.validators.ValidationError(str(e))

        self.validated_credential = validated_credential


class ReAuthenticateForm(PasswordMixin, wtforms.Form):
    __params__ = [
        "username",
        "password",
        "next_route",
        "next_route_matchdict",
        "next_route_query",
    ]

    username = wtforms.fields.HiddenField(
        validators=[wtforms.validators.InputRequired()]
    )
    next_route = wtforms.fields.HiddenField(
        validators=[wtforms.validators.InputRequired()]
    )
    next_route_matchdict = wtforms.fields.HiddenField(
        validators=[wtforms.validators.InputRequired()]
    )
    next_route_query = wtforms.fields.HiddenField(
        validators=[wtforms.validators.InputRequired()]
    )

    def __init__(self, *args, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service


class RecoveryCodeAuthenticationForm(
    RecoveryCodeValueMixin, _TwoFactorAuthenticationForm
):
    def validate_recovery_code_value(self, field):
        recovery_code_value = field.data.encode("utf-8").strip()

        try:
            self.user_service.check_recovery_code(self.user_id, recovery_code_value)
            send_recovery_code_used_email(
                self.request, self.user_service.get_user(self.user_id)
            )
        except (InvalidRecoveryCode, NoRecoveryCodes):
            user = self.user_service.get_user(self.user_id)
            user.record_event(
                tag=EventTag.Account.LoginFailure,
                request=self.request,
                additional={"reason": "invalid_recovery_code"},
            )
            raise wtforms.validators.ValidationError(_("Invalid recovery code."))
        except BurnedRecoveryCode:
            user = self.user_service.get_user(self.user_id)
            user.record_event(
                tag=EventTag.Account.LoginFailure,
                request=self.request,
                additional={"reason": "burned_recovery_code"},
            )
            raise wtforms.validators.ValidationError(
                _("Recovery code has been previously used.")
            )


class RequestPasswordResetForm(wtforms.Form):
    username_or_email = wtforms.StringField(
        validators=[
            wtforms.validators.InputRequired(),
            PreventNullBytesValidator(),
        ]
    )

    def validate_username_or_email(self, field):
        """
        Check if the input is structurally correct, i.e. either a string or email.
        Further validation happens in the View.
        """
        if "@" in field.data:
            # Additional checks for the validity of the address
            try:
                email_validator.validate_email(field.data, check_deliverability=True)
            except email_validator.EmailNotValidError as e:
                raise wtforms.validators.ValidationError(
                    message=INVALID_EMAIL_MESSAGE
                ) from e
        else:
            # the regexp below must match the CheckConstraint
            # for the username field in accounts.models.User
            if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*[a-zA-Z0-9]$", field.data):
                raise wtforms.validators.ValidationError(
                    message=_("The username isn't valid. Try again.")
                )


class ResetPasswordForm(NewPasswordMixin, wtforms.Form):
    pass
