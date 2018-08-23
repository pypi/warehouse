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

import pyotp
import wtforms

from warehouse import forms
from warehouse.accounts.forms import (
    AuthenticationCodeMixin,
    NewEmailMixin,
    NewPasswordMixin,
    PasswordMixin,
)


class RoleNameMixin:

    role_name = wtforms.SelectField(
        "Select role",
        choices=[("Maintainer", "Maintainer"), ("Owner", "Owner")],
        validators=[wtforms.validators.DataRequired(message="Select role")],
    )


class UsernameMixin:

    username = wtforms.StringField(
        validators=[wtforms.validators.DataRequired(message="Specify username")]
    )

    def validate_username(self, field):
        userid = self.user_service.find_userid(field.data)

        if userid is None:
            raise wtforms.validators.ValidationError(
                "No user found with that username. Try again."
            )


class CreateRoleForm(RoleNameMixin, UsernameMixin, forms.Form):
    def __init__(self, *args, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service


class ChangeRoleForm(RoleNameMixin, forms.Form):
    pass


class SaveAccountForm(forms.Form):

    __params__ = ["name"]

    name = wtforms.StringField()


class AddEmailForm(NewEmailMixin, forms.Form):

    __params__ = ["email"]

    def __init__(self, *args, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service


class ChangePasswordForm(PasswordMixin, NewPasswordMixin, forms.Form):

    __params__ = ["password", "new_password", "password_confirm"]

    def __init__(self, *args, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service


class AuthenticationSeedMixin:

    authentication_seed = wtforms.HiddenField(
        validators=[
            wtforms.validators.DataRequired(),
            wtforms.validators.Regexp(
                r"^[A-Z2-7]{16}$",
                message=(
                    "Invalid authentication seed. "
                    "Authentication seeds must be a 16-character base32 value."
                ),
            ),
        ],
        default=pyotp.random_base32,
    )


class MfaConfigurationForm(
    AuthenticationCodeMixin, AuthenticationSeedMixin, forms.Form
):

    __params__ = ["authentication_code", "authentication_seed"]

    def __init__(self, *args, user_service, email, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service
        self.totp = pyotp.totp.TOTP(self.authentication_seed.data)
        self.provisioning_uri = self.totp.provisioning_uri(email, issuer_name="PyPI")

    def validate_authentication_code(self, field):
        authentication_code = field.data

        valid = self.totp.verify(authentication_code)

        if not valid:
            raise wtforms.validators.ValidationError(
                "Invalid authentication code. "
                "Please ensure your system's time is correct."
            )
