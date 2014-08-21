# Copyright 2014 Donald Stufft
#
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
import re
from warehouse import forms


class UsernameValidator(forms.validators.Regexp):
    """ validator specifically for a warehouse username """

    def __init__(self, message=None):
        super().__init__(r"^[A-Z0-9]([A-Z0-9._-]*[A-Z0-9])?$", re.I, message)

    def __call__(self, form, field):
        message = self.message or field.gettext(
            "Username must begin and end with alphanumeric, "
            "the characters \"._-\" are allowed in the middle"
        )
        super().__call__(form, field, message)

_username_field = forms.StringField(
    validators=[
        forms.validators.Required(),
        forms.validators.Length(min=4, max=25),
        UsernameValidator()
    ]
)


class LoginForm(forms.Form):

    username = _username_field

    password = forms.PasswordField()

    def __init__(self, *args, authenticator, **kwargs):
        super(LoginForm, self).__init__(*args, **kwargs)

        self.authenticate = authenticator

    def validate_username(self, field):
        if not self.authenticate(field.data, self.password.data):
            raise forms.ValidationError(
                self.gettext("Invalid username or password")
            )


class RegisterForm(forms.Form):
    """
    The requirements carried over from pypi are:

    * username: begin and end with alphanumeric, allowing ._- in the middle
    * email must be alphanumeric or in ._+@-
    """

    username = _username_field

    email = forms.StringField(
        validators=[
            forms.validators.Email()
        ]
    )

    password = forms.PasswordField()

    confirm_password = forms.PasswordField()

    def __init__(self, *args,
                 is_existing_username,
                 is_existing_email,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self._is_existing_username = is_existing_username
        self._is_existing_email = is_existing_email

    def validate_username(self, field):
        if self._is_existing_username(field.data):
            raise forms.ValidationError(
                self.gettext("Username already exists!")
            )

    def validate_email(self, field):
        if self._is_existing_email(field.data):
            raise forms.ValidationError(
                self.gettext("Email already exists!")
            )

    def validate_confirm_password(self, field):
        if not self.password.data == field.data:
            raise forms.ValidationError(
                self.gettext("Passwords do not match!")
            )
