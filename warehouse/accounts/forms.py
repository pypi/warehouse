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

from warehouse import forms, recaptcha
from warehouse.accounts.interfaces import TooManyFailedLogins


class UsernameMixin:

    username = wtforms.StringField(
        validators=[
            wtforms.validators.DataRequired(),
        ],
    )

    def validate_username(self, field):
        userid = self.user_service.find_userid(field.data)

        if userid is None:
            raise wtforms.validators.ValidationError(
                "No user found with that username."
            )


class NewUsernameMixin:

    username = wtforms.StringField(
        validators=[
            wtforms.validators.DataRequired(),
            wtforms.validators.Length(
                max=50,
                message=(
                    "The username you have chosen is too long. Please choose "
                    "a username with under 50 characters."
                )
            ),
            # the regexp below must match the CheckConstraint
            # for the username field in accounts.models.User
            wtforms.validators.Regexp(
                r'^[a-zA-Z0-9][a-zA-Z0-9._-]*[a-zA-Z0-9]$',
                message=(
                    "The username is invalid. Usernames "
                    "must be composed of letters, numbers, "
                    "dots, hyphens and underscores. And must "
                    "also start and finish with a letter or number. "
                    "Please choose a different username."
                )
            )
        ],
    )

    def validate_username(self, field):
        if self.user_service.find_userid(field.data) is not None:
            raise wtforms.validators.ValidationError(
                "This username is already being used by another "
                "account. Please choose a different username."
            )


class PasswordMixin:

    password = wtforms.PasswordField(
        validators=[
            wtforms.validators.DataRequired(),
        ],
    )


class NewPasswordMixin:

    password = wtforms.PasswordField(
        validators=[
            wtforms.validators.DataRequired(),
            forms.PasswordStrengthValidator(
                user_input_fields=["full_name", "username", "email"],
            ),
        ],
    )

    password_confirm = wtforms.PasswordField(
        validators=[
            wtforms.validators.DataRequired(),
            wtforms.validators.EqualTo(
                "password", "Your passwords do not match. Please try again."
            ),
        ],
    )


class NewEmailMixin:

    email = wtforms.fields.html5.EmailField(
        validators=[
            wtforms.validators.DataRequired(),
            wtforms.validators.Email(
                message=(
                    "The email address you have chosen is not a valid "
                    "format. Please try again."
                )
            ),
        ],
    )

    def validate_email(self, field):
        if self.user_service.find_userid_by_email(field.data) is not None:
            raise wtforms.validators.ValidationError(
                "This email address is already being used by another account. "
                "Please use a different email."
            )
        domain = field.data.split('@')[-1]
        if domain in disposable_email_domains.blacklist:
            raise wtforms.validators.ValidationError(
                "Sorry, you cannot create an account with an email address "
                "from this domain. Please use a different email."
            )


class RegistrationForm(
        NewPasswordMixin, NewUsernameMixin, NewEmailMixin, forms.Form):

    full_name = wtforms.StringField()
    g_recaptcha_response = wtforms.StringField()

    def __init__(self, *args, recaptcha_service, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service
        self.recaptcha_service = recaptcha_service

    def validate_g_recaptcha_response(self, field):
        # do required data validation here due to enabled flag being required
        if self.recaptcha_service.enabled and not field.data:
            raise wtforms.validators.ValidationError("Recaptcha error.")
        try:
            self.recaptcha_service.verify_response(field.data)
        except recaptcha.RecaptchaError:
            # TODO: log error
            # don't want to provide the user with any detail
            raise wtforms.validators.ValidationError("Recaptcha error.")


class LoginForm(PasswordMixin, UsernameMixin, forms.Form):

    def __init__(self, *args, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service

    def validate_password(self, field):
        userid = self.user_service.find_userid(self.username.data)
        if userid is not None:
            try:
                if not self.user_service.check_password(userid, field.data):
                    raise wtforms.validators.ValidationError(
                        "The username and password combination you have "
                        "provided is invalid. Please try again."
                    )
            except TooManyFailedLogins:
                raise wtforms.validators.ValidationError(
                    "There have been too many unsuccessful login attempts, "
                    "please try again later."
                ) from None


class RequestPasswordResetForm(UsernameMixin, forms.Form):

    def __init__(self, *args, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service


class ResetPasswordForm(NewPasswordMixin, forms.Form):

    # These fields are here to provide the various user-defined fields to the
    # PasswordStrengthValidator of the NewPasswordMixin, to ensure that the
    # newly set password doesn't contain any of them
    full_name = wtforms.StringField()
    username = wtforms.StringField()
    email = wtforms.StringField()
