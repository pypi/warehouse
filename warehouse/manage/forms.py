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

import wtforms

import warehouse.utils.otp as otp
import warehouse.utils.webauthn as webauthn

from warehouse import forms
from warehouse.accounts.forms import (
    NewEmailMixin,
    NewPasswordMixin,
    PasswordMixin,
    TOTPValueMixin,
    WebAuthnCredentialMixin,
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

    def __init__(self, *args, user_service, user_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service
        self.user_id = user_id


class ChangePasswordForm(PasswordMixin, NewPasswordMixin, forms.Form):

    __params__ = ["password", "new_password", "password_confirm"]

    def __init__(self, *args, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service


class DeleteTOTPForm(UsernameMixin, forms.Form):

    __params__ = ["confirm_username"]

    def __init__(self, *args, user_service, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service


class ProvisionTOTPForm(TOTPValueMixin, forms.Form):

    __params__ = ["totp_value"]

    def __init__(self, *args, totp_secret, **kwargs):
        super().__init__(*args, **kwargs)
        self.totp_secret = totp_secret

    def validate_totp_value(self, field):
        totp_value = field.data.encode("utf8")
        if not otp.verify_totp(self.totp_secret, totp_value):
            raise wtforms.validators.ValidationError("Invalid TOTP code. Try again?")


class DeleteWebAuthnForm(UsernameMixin, forms.Form):
    __params__ = ["confirm_username", "label"]

    label = wtforms.StringField(
        validators=[wtforms.validators.DataRequired(message="Specify a label")]
    )

    def __init__(self, *args, user_service, user_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_service = user_service
        self.user_id = user_id

    def validate_label(self, field):
        label = field.data

        webauthn = self.user_service.get_webauthn_by_label(self.user_id, label)
        if webauthn is None:
            raise wtforms.validators.ValidationError("No WebAuthn key with given label")
        self.webauthn = webauthn


class ProvisionWebAuthnForm(WebAuthnCredentialMixin, forms.Form):
    __params__ = ["label", "credential"]

    label = wtforms.StringField(
        validators=[wtforms.validators.DataRequired(message="Specify a label")]
    )

    def __init__(
        self, *args, user_service, user_id, challenge, rp_id, origin, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.user_service = user_service
        self.user_id = user_id
        self.challenge = challenge
        self.rp_id = rp_id
        self.origin = origin

    def validate_credential(self, field):
        try:
            credential_dict = json.loads(field.data.encode("utf8"))
        except json.JSONDecodeError:
            raise wtforms.validators.ValidationError(
                "Invalid WebAuthn credential: Bad payload"
            )

        try:
            validated_credential = self.user_service.verify_webauthn_credential(
                credential_dict,
                challenge=self.challenge,
                rp_id=self.rp_id,
                origin=self.origin,
            )
        except webauthn.RegistrationRejectedException as e:
            raise wtforms.validators.ValidationError(str(e))

        self.validated_credential = validated_credential

    def validate_label(self, field):
        label = field.data

        if self.user_service.get_webauthn_by_label(self.user_id, label) is not None:
            raise wtforms.validators.ValidationError(f"Label '{label}' already in use")
