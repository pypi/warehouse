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

import disposable_email_domains
import wtforms
import wtforms.fields.html5
import jinja2

from warehouse import forms
from warehouse.accounts.interfaces import TooManyFailedLogins
from warehouse.accounts.models import DisableReason
from warehouse.email import send_password_compromised_email


class UsernameMixin:

    username = wtforms.StringField(validators=[wtforms.validators.DataRequired()])

    def validate_username(self, field):
        userid = self.user_service.find_userid(field.data)

        if userid is None:
            raise wtforms.validators.ValidationError("No user found with that username")


class NewUsernameMixin:

    username = wtforms.StringField(
        validators=[
            wtforms.validators.DataRequired(),
            wtforms.validators.Length(
                max=50, message=("Choose a username with 50 characters or less.")
            ),
            # the regexp below must match the CheckConstraint
            # for the username field in accounts.models.User
            wtforms.validators.Regexp(
                r"^[a-zA-Z0-9][a-zA-Z0-9._-]*[a-zA-Z0-9]$",
                message=(
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
                "This username is already being used by another "
                "account. Choose a different username."
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
                        "The password is invalid. Try again."
                    )
            except TooManyFailedLogins:
                raise wtforms.validators.ValidationError(
                    "There have been too many unsuccessful login attempts, "
                    "try again later."
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
                "new_password", "Your passwords don't match. Try again."
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
            wtforms.validators.Email(
                message=("The email address isn't valid. Try again.")
            ),
        ]
    )

    def validate_email(self, field):
        if self.user_service.find_userid_by_email(field.data) is not None:
            raise wtforms.validators.ValidationError(
                "This email address is already being used by another account. "
                "Use a different email."
            )
        domain = field.data.split("@")[-1]
        if domain in disposable_email_domains.blacklist:
            raise wtforms.validators.ValidationError(
                "You can't create an account with an email address "
                "from this domain. Use a different email."
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
                message=(
                    "The name is too long. "
                    "Choose a name with 100 characters or less."
                ),
            )
        ]
    )

    def __init__(self, *args, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service


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
                send_password_compromised_email(self.request, user)
                self.user_service.disable_password(
                    user.id, reason=DisableReason.CompromisedPassword
                )
                raise wtforms.validators.ValidationError(
                    jinja2.Markup(self.breach_service.failure_message)
                )


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
                "No user found with that username or email"
            )


class ResetPasswordForm(NewPasswordMixin, forms.Form):

    pass
