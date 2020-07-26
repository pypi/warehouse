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

import json

from email.headerregistry import Address

import disposable_email_domains
import jinja2
import wtforms
import wtforms.fields.html5

import warehouse.utils.webauthn as webauthn

from warehouse import forms
from warehouse.accounts.interfaces import TooManyFailedLogins
from warehouse.accounts.models import DisableReason
from warehouse.email import send_password_compromised_email_hibp
from warehouse.i18n import localize as _
from warehouse.utils.otp import TOTP_LENGTH


class UsernameMixin:

    username = wtforms.StringField(validators=[wtforms.validators.DataRequired()])

    def validate_username(self, field):
        userid = self.user_service.find_userid(field.data)

        if userid is None:
            raise wtforms.validators.ValidationError(
                _("No user found with that username")
            )


class TOTPValueMixin:

    totp_value = wtforms.StringField(
        validators=[
            wtforms.validators.DataRequired(),
            wtforms.validators.Regexp(
                rf"^ *([0-9] *){{{TOTP_LENGTH}}}$",
                message=_(
                    "TOTP code must be ${totp_length} digits.",
                    mapping={"totp_length": TOTP_LENGTH},
                ),
            ),
        ]
    )


class WebAuthnCredentialMixin:

    credential = wtforms.StringField(wtforms.validators.DataRequired())


class RecoveryCodeValueMixin:

    recovery_code_value = wtforms.StringField(
        validators=[wtforms.validators.DataRequired()]
    )


class NewUsernameMixin:

    username = wtforms.StringField(
        validators=[
            wtforms.validators.DataRequired(),
            wtforms.validators.Length(
                max=50, message=_("Choose a username with 50 characters or less.")
            ),
            # the regexp below must match the CheckConstraint
            # for the username field in accounts.models.User
            wtforms.validators.Regexp(
                r"^[a-zA-Z0-9][a-zA-Z0-9._-]*[a-zA-Z0-9]$",
                message=_(
                    "The username is invalid. Usernames "
                    "must be composed of letters, numbers, "
                    "dots, hyphens and underscores. And must "
                    "also start and finish with a letter or number. "
                    "Choose a different username."
                ),
            ),
        ]
    )

    def validate_username(self, field):
        if self.user_service.find_userid(field.data) is not None:
            raise wtforms.validators.ValidationError(
                _(
                    "This username is already being used by another "
                    "account. Choose a different username."
                )
            )


class PasswordMixin:

    password = wtforms.PasswordField(validators=[wtforms.validators.DataRequired()])

    def __init__(self, *args, check_password_metrics_tags=None, **kwargs):
        self._check_password_metrics_tags = check_password_metrics_tags
        super().__init__(*args, **kwargs)

    def validate_password(self, field):
        userid = self.user_service.find_userid(self.username.data)
        if userid is not None:
            try:
                if not self.user_service.check_password(
                    userid, field.data, tags=self._check_password_metrics_tags
                ):
                    raise wtforms.validators.ValidationError(
                        _("The password is invalid. Try again.")
                    )
            except TooManyFailedLogins as err:
                raise wtforms.validators.ValidationError(
                    _(
                        "There have been too many unsuccessful login attempts. "
                        "You have been locked out for {0} minutes. "
                        "Please try again later.".format(err.resets_in.total_seconds())
                    )
                ) from None


class NewPasswordMixin:

    new_password = wtforms.PasswordField(
        validators=[
            wtforms.validators.DataRequired(),
            forms.PasswordStrengthValidator(
                user_input_fields=["full_name", "username", "email"]
            ),
        ]
    )

    password_confirm = wtforms.PasswordField(
        validators=[
            wtforms.validators.DataRequired(),
            wtforms.validators.EqualTo(
                "new_password", message=_("Your passwords don't match. Try again.")
            ),
        ]
    )

    # These fields are here to provide the various user-defined fields to the
    # PasswordStrengthValidator of the new_password field, to ensure that the
    # newly set password doesn't contain any of them
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
                jinja2.Markup(self._breach_service.failure_message)
            )


class NewEmailMixin:

    email = wtforms.fields.html5.EmailField(
        validators=[
            wtforms.validators.DataRequired(),
            wtforms.validators.Regexp(
                r".+@.+\..+", message=_("The email address isn't valid. Try again.")
            ),
        ]
    )

    def validate_email(self, field):
        # Additional checks for the validity of the address
        try:
            Address(addr_spec=field.data)
        except ValueError:
            raise wtforms.validators.ValidationError(
                _("The email address isn't valid. Try again.")
            )

        # Check if the domain is valid
        domain = field.data.split("@")[-1]

        if domain in disposable_email_domains.blacklist:
            raise wtforms.validators.ValidationError(
                _(
                    "You can't use an email address from this domain. Use a "
                    "different email."
                )
            )

        # Check if this email address is already in use
        userid = self.user_service.find_userid_by_email(field.data)

        if userid and userid == self.user_id:
            raise wtforms.validators.ValidationError(
                _(
                    "This email address is already being used by this account. "
                    "Use a different email."
                )
            )
        if userid:
            raise wtforms.validators.ValidationError(
                _(
                    "This email address is already being used "
                    "by another account. Use a different email."
                )
            )


class HoneypotMixin:

    """ A mixin to catch spammers. This field should always be blank """

    confirm_form = wtforms.StringField()


class RegistrationForm(
    NewUsernameMixin, NewEmailMixin, NewPasswordMixin, HoneypotMixin, forms.Form
):

    full_name = wtforms.StringField(
        validators=[
            wtforms.validators.Length(
                max=100,
                message=_(
                    "The name is too long. "
                    "Choose a name with 100 characters or less."
                ),
            )
        ]
    )

    def __init__(self, *args, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service
        self.user_id = None


class LoginForm(PasswordMixin, UsernameMixin, forms.Form):
    def __init__(self, *args, request, user_service, breach_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.user_service = user_service
        self.breach_service = breach_service

    def validate_password(self, field):
        # Before we try to validate the user's password, we'll first to check to see if
        # they are disabled.
        userid = self.user_service.find_userid(self.username.data)
        if userid is not None:
            is_disabled, disabled_for = self.user_service.is_disabled(userid)
            if is_disabled and disabled_for == DisableReason.CompromisedPassword:
                raise wtforms.validators.ValidationError(
                    jinja2.Markup(self.breach_service.failure_message)
                )

        # Do our typical validation of the password.
        super().validate_password(field)

        # If we have a user ID, then we'll go and check it against our breached password
        # service. If the password has appeared in a breach or is otherwise compromised
        # we will disable the user and reject the login.
        if userid is not None:
            if self.breach_service.check_password(
                field.data, tags=["method:auth", "auth_method:login_form"]
            ):
                user = self.user_service.get_user(userid)
                send_password_compromised_email_hibp(self.request, user)
                self.user_service.disable_password(
                    user.id, reason=DisableReason.CompromisedPassword
                )
                raise wtforms.validators.ValidationError(
                    jinja2.Markup(self.breach_service.failure_message)
                )


class _TwoFactorAuthenticationForm(forms.Form):
    def __init__(self, *args, user_id, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_id = user_id
        self.user_service = user_service


class TOTPAuthenticationForm(TOTPValueMixin, _TwoFactorAuthenticationForm):
    def validate_totp_value(self, field):
        totp_value = field.data.replace(" ", "").encode("utf8")

        if not self.user_service.check_totp_value(self.user_id, totp_value):
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
            assertion_dict = json.loads(field.data.encode("utf8"))
        except json.JSONDecodeError:
            raise wtforms.validators.ValidationError(
                _("Invalid WebAuthn assertion: Bad payload")
            )

        try:
            validated_credential = self.user_service.verify_webauthn_assertion(
                self.user_id,
                assertion_dict,
                challenge=self.challenge,
                origin=self.origin,
                rp_id=self.rp_id,
            )

        except webauthn.AuthenticationRejectedException as e:
            raise wtforms.validators.ValidationError(str(e))

        self.validated_credential = validated_credential


class RecoveryCodeAuthenticationForm(
    RecoveryCodeValueMixin, _TwoFactorAuthenticationForm
):
    def validate_recovery_code_value(self, field):
        recovery_code_value = field.data.encode("utf-8")

        if not self.user_service.check_recovery_code(self.user_id, recovery_code_value):
            raise wtforms.validators.ValidationError(_("Invalid recovery code."))


class RequestPasswordResetForm(forms.Form):
    username_or_email = wtforms.StringField(
        validators=[wtforms.validators.DataRequired()]
    )

    def __init__(self, *args, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service

    def validate_username_or_email(self, field):
        username_or_email = self.user_service.get_user_by_username(field.data)
        if username_or_email is None:
            username_or_email = self.user_service.get_user_by_email(field.data)
        if username_or_email is None:
            raise wtforms.validators.ValidationError(
                _("No user found with that username or email")
            )


class ResetPasswordForm(NewPasswordMixin, forms.Form):

    pass
