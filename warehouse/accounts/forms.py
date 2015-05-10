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

import wtforms

from warehouse import forms


def validate_legacy_username(form, username_field):
    """ ensures that the username satisfies legacy pypi requirements. """
    username = username_field.data
    valid = username[0].isalnum() and username[-1].isalnum()
    if not valid:
        raise wtforms.validators.ValidationError(
            "Username must start and end with an alphanumeric character."
        )

    for c in username:
        if not (c.isalnum() or c in '._-'):
            raise wtforms.validators.ValidationError(
                "Username can only contain alphanumeric characters, "
                "or those in \"._-\""
            )


class LoginForm(forms.Form):

    username = wtforms.StringField(
        validators=[
            wtforms.validators.DataRequired(),
            wtforms.validators.Length(max=50),
        ],
    )

    password = wtforms.PasswordField(
        validators=[
            wtforms.validators.DataRequired(),
        ],
    )

    def __init__(self, *args, login_service, **kwargs):
        super().__init__(*args, **kwargs)

        self.login_service = login_service

    def validate_username(self, field):
        userid = self.login_service.find_userid(field.data)

        if userid is None:
            raise wtforms.validators.ValidationError("Invalid user.")

    def validate_password(self, field):
        userid = self.login_service.find_userid(self.username.data)
        if userid is not None:
            if not self.login_service.check_password(userid, field.data):
                raise wtforms.validators.ValidationError("Invalid password.")


class RegisterForm(forms.Form):

    email = wtforms.StringField(
        validators=[
            wtforms.validators.DataRequired(),
            wtforms.validators.Length(max=50),
        ],
    )

    username = wtforms.StringField(
        validators=[
            wtforms.validators.DataRequired(),
            wtforms.validators.Length(max=50),
            validate_legacy_username
        ],
    )

    password = wtforms.PasswordField(
        validators=[
            wtforms.validators.DataRequired(),
        ],
    )

    confirm = wtforms.PasswordField(
        validators=[
            wtforms.validators.DataRequired(),
        ],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def validate_confirm(self, field):
        if field.data != self.password.data:
            raise wtforms.validators.ValidationError(
                "Password and confirm must match!"
            )
